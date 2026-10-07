"""list_usages：扫描 library + 9B build 索引 stub。"""

from __future__ import annotations

from typing import Any, Protocol

from .protocol import FactorCollection, FactorLibraryEntry, FactorPortfolioSpec


class _RegistryLike(Protocol):
    def get_feature(self, feature_ref: str) -> Any: ...


def list_usages(
    factor_ref: str,
    *,
    entries: list[FactorLibraryEntry],
    collections: list[FactorCollection],
    portfolios: list[FactorPortfolioSpec],
    registry: _RegistryLike | None = None,
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {
        "library_entries": [],
        "collections": [],
        "portfolios": [],
        "feature_builds": [],
    }
    for e in entries:
        if e.factor_ref == factor_ref:
            out["library_entries"].append(e.entry_id)
    for c in collections:
        if factor_ref in c.member_refs:
            out["collections"].append(c.collection_id)
    for p in portfolios:
        if factor_ref in p.member_refs:
            out["portfolios"].append(p.portfolio_id)
    if registry is not None:
        try:
            feat = registry.get_feature(factor_ref)
            sidecar = getattr(feat, "definition", None) or {}
            if isinstance(sidecar, dict) and sidecar.get("library_entry_id"):
                out["feature_builds"].append(str(sidecar.get("library_entry_id")))
        except Exception:
            pass
    return out


__all__ = ["list_usages"]
