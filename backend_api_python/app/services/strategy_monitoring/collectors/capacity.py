"""Phase 8F：Capacity 维度（简化标量）。"""

from __future__ import annotations

from typing import Any, Mapping

from ..identity import build_metric_id
from ..protocol import HealthStatus, MonitoringMetric


def _f(src: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    if key not in src or src[key] is None:
        return default
    try:
        return float(src[key])
    except (TypeError, ValueError):
        return default


def collect_capacity(
    strategy_code: str,
    *,
    collected_at: str,
    session_id: str,
    section: Mapping[str, Any],
) -> list[MonitoringMetric]:
    util = _f(section, "capacity_util", 0.4)
    health: HealthStatus = "HEALTHY"
    if util >= 0.95:
        health = "CRITICAL"
    elif util >= 0.80:
        health = "WARNING"
    return [
        MonitoringMetric(
            metric_id=build_metric_id(
                strategy_code=strategy_code,
                category="CAPACITY",
                name="capacity_util",
                collected_at=collected_at,
            ),
            strategy_code=strategy_code,
            category="CAPACITY",
            name="capacity_util",
            value=util,
            health=health,
            collected_at=collected_at,
            session_id=session_id,
        )
    ]


__all__ = ["collect_capacity"]
