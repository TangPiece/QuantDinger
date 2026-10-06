"""group_evaluation_hash。"""

from __future__ import annotations

import hashlib

from app.services.research_data.hashing import canonical_json

from .protocol import GroupSpec


def normalize_group_spec(spec: GroupSpec, *, resolved_direction: str) -> dict:
    """规范化 hash 输入（direction 用解析后的 POSITIVE/NEGATIVE）。"""
    return {
        "evaluation_hash": spec.evaluation_hash,
        "group_count": int(spec.group_count),
        "weighting_method": spec.weighting_method,
        "direction": resolved_direction,
        "portfolio_mode": spec.portfolio_mode,
        "horizons": list(spec.horizons) if spec.horizons is not None else None,
        "min_cross_section_size": spec.min_cross_section_size,
        "allowed_sample_status": sorted(spec.allowed_sample_status),
        "cost_model": spec.cost_model.model_dump(mode="json"),
        "group_version": spec.group_version,
    }


def compute_group_evaluation_hash(
    spec: GroupSpec, *, resolved_direction: str
) -> str:
    """稳定 group_evaluation_hash。"""
    payload = normalize_group_spec(spec, resolved_direction=resolved_direction)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
