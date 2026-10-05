"""两次 Experiment 结果可复现性比较。"""

from __future__ import annotations

import math
from typing import Any

from .runner import ExperimentResult


def _num_close(a: Any, b: Any, *, rtol: float = 1e-9, atol: float = 1e-12) -> bool:
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    if math.isnan(fa) and math.isnan(fb):
        return True
    if math.isnan(fa) or math.isnan(fb):
        return False
    return abs(fa - fb) <= atol + rtol * max(abs(fa), abs(fb))


def is_reproducible(
    a: ExperimentResult,
    b: ExperimentResult,
    *,
    metric_keys: tuple[str, ...] | None = None,
) -> bool:
    """同 repro / dataset / prediction / signal artifact；metrics 数值容差。"""
    if a.experiment_id != b.experiment_id:
        return False
    if a.repro_fingerprint != b.repro_fingerprint:
        return False
    if a.dataset_hash != b.dataset_hash:
        return False
    if a.prediction_fingerprint != b.prediction_fingerprint:
        return False
    if a.signal_artifact_id != b.signal_artifact_id:
        return False
    if a.model_artifact_id != b.model_artifact_id:
        return False
    keys = metric_keys or tuple(
        sorted(set(a.metrics.keys()) & set(b.metrics.keys()))
    )
    for k in keys:
        if k not in a.metrics or k not in b.metrics:
            return False
        if not _num_close(a.metrics[k], b.metrics[k]):
            return False
    return True
