"""stability_hash：钉住 evaluation_hash + StabilitySpec 关键字段。"""

from __future__ import annotations

import hashlib

from app.services.research_data.hashing import canonical_json

from .protocol import StabilitySpec


def normalize_stability_spec(
    spec: StabilitySpec, *, resolved_direction: str
) -> dict:
    """规范化 hash 输入（direction 用解析后的 POSITIVE/NEGATIVE）。"""
    return {
        "evaluation_hash": spec.evaluation_hash,
        "rolling_windows": list(spec.rolling_windows),
        "decay_horizons": list(spec.decay_horizons)
        if spec.decay_horizons is not None
        else None,
        "regime_types": list(spec.regime_types),
        "min_cross_section_size": int(spec.min_cross_section_size),
        "min_rolling_samples": int(spec.min_rolling_samples),
        "allowed_sample_status": sorted(spec.allowed_sample_status),
        "direction": resolved_direction,
        "group_count": int(spec.group_count),
        "portfolio_mode": spec.portfolio_mode,
        "cost_model": spec.cost_model.model_dump(mode="json"),
        "stability_version": spec.stability_version,
    }


def compute_stability_hash(
    spec: StabilitySpec, *, resolved_direction: str
) -> str:
    """稳定 stability_hash。"""
    payload = normalize_stability_spec(spec, resolved_direction=resolved_direction)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
