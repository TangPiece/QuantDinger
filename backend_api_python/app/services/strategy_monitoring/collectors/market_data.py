"""Phase 8F：MARKET_DATA 新鲜度。"""

from __future__ import annotations

from typing import Any, Mapping

from ..identity import build_metric_id
from ..protocol import HealthStatus, MonitoringMetric, MonitorPolicyRecord


def _f(src: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    if key not in src or src[key] is None:
        return default
    try:
        return float(src[key])
    except (TypeError, ValueError):
        return default


def _staleness_health(staleness: float, policy: MonitorPolicyRecord) -> HealthStatus:
    md = policy.market_data
    if staleness > md.critical_staleness_seconds:
        return "CRITICAL"
    if staleness > md.max_staleness_seconds:
        return "WARNING"
    return "HEALTHY"


def collect_market_data(
    strategy_code: str,
    *,
    collected_at: str,
    session_id: str,
    section: Mapping[str, Any],
    policy: MonitorPolicyRecord,
) -> list[MonitoringMetric]:
    stale = _f(section, "staleness_seconds", _f(section, "market_data_staleness", 30.0))
    health = _staleness_health(stale, policy)
    return [
        MonitoringMetric(
            metric_id=build_metric_id(
                strategy_code=strategy_code,
                category="MARKET_DATA",
                name="staleness_seconds",
                collected_at=collected_at,
            ),
            strategy_code=strategy_code,
            category="MARKET_DATA",
            name="staleness_seconds",
            value=stale,
            unit="s",
            health=health,
            collected_at=collected_at,
            session_id=session_id,
        )
    ]


__all__ = ["collect_market_data"]
