"""neutralization_hash：钉住源 dataset + method + targets + exposure versions。"""

from __future__ import annotations

import hashlib

from app.services.research_data.hashing import canonical_json

from .protocol import NeutralizationSpec


def normalize_neutralization_spec(
    spec: NeutralizationSpec, *, factor_dataset_hash: str
) -> dict:
    """规范化 hash 输入（不含 runtime metadata）。"""
    return {
        "factor_dataset_id": spec.factor_dataset_id,
        "factor_dataset_hash": factor_dataset_hash,
        "method": spec.method,
        "targets": list(spec.targets),
        "size_metric_code": spec.size_metric_code,
        "size_transform": spec.size_transform,
        "industry_version": spec.industry_version,
        "industry_panel_uri": spec.industry_panel_uri or "",
        "include_intercept": bool(spec.include_intercept),
        "min_cross_section_size": int(spec.min_cross_section_size),
        "strength": spec.strength,
        "exposure_dataset_versions": dict(
            sorted((spec.exposure_dataset_versions or {}).items())
        ),
        "neutralization_version": spec.neutralization_version,
    }


def compute_neutralization_hash(
    spec: NeutralizationSpec, *, factor_dataset_hash: str
) -> str:
    """稳定 neutralization_hash。"""
    payload = normalize_neutralization_spec(
        spec, factor_dataset_hash=factor_dataset_hash
    )
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
