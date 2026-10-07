"""FeatureUniverse：钉住 FeatureSet 或显式列列表。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

class _FeatureFactorLike(Protocol):
    def get_manifest(self, feature_set_ref: str) -> Any: ...


@dataclass(frozen=True)
class FeatureUniverse:
    columns: tuple[str, ...]
    feature_set_ref: str = ""
    feature_set_hash: str = ""

    @property
    def size(self) -> int:
        return len(self.columns)


def compute_feature_set_hash(columns: list[str], *, feature_set_ref: str = "") -> str:
    payload = {
        "feature_set_ref": feature_set_ref,
        "columns": sorted({c.lower() for c in columns}),
    }
    from app.services.research_data.hashing import canonical_json
    import hashlib

    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def resolve_feature_universe(
    *,
    feature_set_ref: str = "",
    feature_columns: list[str] | None = None,
    factor_svc: _FeatureFactorLike | None = None,
    max_columns: int = 32,
) -> FeatureUniverse:
    cols: list[str] = []
    fs_hash = ""
    if feature_set_ref and factor_svc is not None:
        manifest = factor_svc.get_manifest(feature_set_ref)
        for m in getattr(manifest, "members", []) or []:
            ref = str(m)
            if "@" in ref:
                code = ref.split("@", 1)[0]
                cols.append(code.split(":")[-1] if ":" in code else "close")
            else:
                cols.append(ref)
        fs_hash = getattr(manifest, "feature_set_hash", "") or compute_feature_set_hash(
            cols, feature_set_ref=feature_set_ref
        )
    if feature_columns:
        cols = list(feature_columns)
    if not cols:
        cols = ["close", "open", "high", "low", "volume"]
    cols = sorted({c.lower() for c in cols})[:max_columns]
    if not fs_hash:
        fs_hash = compute_feature_set_hash(cols, feature_set_ref=feature_set_ref)
    return FeatureUniverse(columns=tuple(cols), feature_set_ref=feature_set_ref, feature_set_hash=fs_hash)


__all__ = [
    "FeatureUniverse",
    "compute_feature_set_hash",
    "resolve_feature_universe",
]
