"""metric_hash：钉住 evaluation_hash + MetricSpec + versions。"""

from __future__ import annotations

import hashlib

from app.services.research_data.hashing import canonical_json

from .protocol import MetricSpec


def normalize_metric_spec(spec: MetricSpec) -> dict:
    """规范化 hash 输入（不含 runtime metadata）。"""
    return {
        "evaluation_hash": spec.evaluation_hash,
        "horizons": list(spec.horizons) if spec.horizons is not None else None,
        "min_cross_section_size": spec.min_cross_section_size,
        "allowed_sample_status": sorted(spec.allowed_sample_status),
        "direction": spec.direction,
        "metric_version": spec.metric_version,
        "calculator_version": spec.calculator_version,
    }


def compute_metric_hash(spec: MetricSpec) -> str:
    """稳定 metric_hash。"""
    payload = normalize_metric_spec(spec)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
