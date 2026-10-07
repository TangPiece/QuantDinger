"""Phase 8F：Execution 维度。"""

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


def _rate_health(rate: float) -> HealthStatus:
    if rate >= 0.15:
        return "CRITICAL"
    if rate >= 0.08:
        return "WARNING"
    return "HEALTHY"


def collect_execution(
    strategy_code: str,
    *,
    collected_at: str,
    session_id: str,
    section: Mapping[str, Any],
) -> list[MonitoringMetric]:
    reject = _f(section, "reject_rate", 0.02)
    slip = _f(section, "slippage_bps", 5.0)
    return [
        MonitoringMetric(
            metric_id=build_metric_id(
                strategy_code=strategy_code,
                category="EXECUTION",
                name="reject_rate",
                collected_at=collected_at,
            ),
            strategy_code=strategy_code,
            category="EXECUTION",
            name="reject_rate",
            value=reject,
            health=_rate_health(reject),
            collected_at=collected_at,
            session_id=session_id,
        ),
        MonitoringMetric(
            metric_id=build_metric_id(
                strategy_code=strategy_code,
                category="EXECUTION",
                name="slippage_bps",
                collected_at=collected_at,
            ),
            strategy_code=strategy_code,
            category="EXECUTION",
            name="slippage_bps",
            value=slip,
            health="HEALTHY" if slip < 25 else "WARNING",
            collected_at=collected_at,
            session_id=session_id,
        ),
    ]


__all__ = ["collect_execution"]
