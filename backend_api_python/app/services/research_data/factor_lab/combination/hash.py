"""combination_hash：钉住成员 dataset_hash + 组合规格。"""

from __future__ import annotations

import hashlib

from app.services.research_data.hashing import canonical_json

from .protocol import CombinationSpec


def normalize_combination_spec(
    spec: CombinationSpec, *, member_hashes: dict[str, str]
) -> dict:
    """规范化 hash 输入。"""
    ids = list(spec.member_factor_dataset_ids)
    return {
        "member_factor_dataset_ids": ids,
        "member_dataset_hashes": {mid: member_hashes.get(mid, "") for mid in ids},
        "normalize": spec.normalize,
        "weight_method": spec.weight_method,
        "member_ic": {k: float(v) for k, v in sorted((spec.member_ic or {}).items())},
        "redundancy_corr_threshold": float(spec.redundancy_corr_threshold),
        "min_cross_section_size": int(spec.min_cross_section_size),
        "missing_policy": spec.missing_policy,
        "combination_version": spec.combination_version,
    }


def compute_combination_hash(
    spec: CombinationSpec, *, member_hashes: dict[str, str]
) -> str:
    """稳定 combination_hash。"""
    payload = normalize_combination_spec(spec, member_hashes=member_hashes)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
