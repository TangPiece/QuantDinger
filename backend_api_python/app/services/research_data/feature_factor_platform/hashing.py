"""FeatureSet hash；Factor hash 复用 factor_lab。"""

from __future__ import annotations

import hashlib
from typing import Sequence

from app.services.research_data.factor_lab.hash import compute_factor_hash
from app.services.research_data.hashing import canonical_json

from .protocol import ENGINE_VERSION


def compute_feature_set_hash(
    *,
    code: str,
    version: str,
    member_refs: Sequence[str],
    processor: str = "",
    schema_version: str = "feature_set@1",
) -> str:
    """feature_set_hash = SHA256(sorted members + processor + schema + engine)。"""
    payload = {
        "code": code,
        "version": version,
        "member_refs": sorted(str(m) for m in (member_refs or [])),
        "processor": processor or "",
        "schema_version": schema_version,
        "engine_version": ENGINE_VERSION,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


__all__ = [
    "compute_factor_hash",
    "compute_feature_set_hash",
]
