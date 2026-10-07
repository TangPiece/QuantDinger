"""Phase 8F：Signal 维度。"""

from __future__ import annotations

from typing import Any, Mapping

from ..identity import build_metric_id
from ..protocol import HealthStatus, MonitoringMetric


def _f(src: Mapping[str, Any], key: str, default: float = 1.0) -> float:
    if key not in src or src[key] is None:
        return default
    try:
        return float(src[key])
    except (TypeError, ValueError):
        return default


def collect_signal(
    strategy_code: str,
    *,
    collected_at: str,
    session_id: str,
    section: Mapping[str, Any],
    feedback_scalars: Mapping[str, float] | None,
) -> list[MonitoringMetric]:
    fb = dict(feedback_scalars or {})
    corr = _f({**fb, **dict(section)}, "signal_correlation", 0.99)
    drift = abs(1.0 - corr)
    health: HealthStatus = "HEALTHY"
    if drift >= 0.30:
        health = "CRITICAL"
    elif drift >= 0.15:
        health = "WARNING"
    return [
        MonitoringMetric(
            metric_id=build_metric_id(
                strategy_code=strategy_code,
                category="SIGNAL",
                name="signal_correlation",
                collected_at=collected_at,
            ),
            strategy_code=strategy_code,
            category="SIGNAL",
            name="signal_correlation",
            value=corr,
            health=health,
            collected_at=collected_at,
            session_id=session_id,
        )
    ]


__all__ = ["collect_signal"]
