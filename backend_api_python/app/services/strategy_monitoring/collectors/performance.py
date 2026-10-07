"""Phase 8F：Performance 维度采集（含 8E scalars）。"""

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


def _health_from_thresholds(value: float, *, warn: float, crit: float, compare: str = "gt") -> HealthStatus:
    if compare in ("gt", "gte"):
        if value >= crit:
            return "CRITICAL"
        if value >= warn:
            return "WARNING"
        return "HEALTHY"
    if value <= crit:
        return "CRITICAL"
    if value <= warn:
        return "WARNING"
    return "HEALTHY"


def collect_performance(
    strategy_code: str,
    *,
    collected_at: str,
    session_id: str,
    section: Mapping[str, Any],
    feedback_scalars: Mapping[str, float] | None,
) -> list[MonitoringMetric]:
    fb = dict(feedback_scalars or {})
    merged = {**fb, **dict(section)}
    metrics_spec = [
        ("shadow_drift", 0.08, 0.15, "gt"),
        ("max_drawdown", 0.12, 0.20, "gt"),
        ("return_gap", 0.05, 0.12, "gt"),
    ]
    out: list[MonitoringMetric] = []
    for name, warn, crit, cmp in metrics_spec:
        val = _f(merged, name)
        if name not in merged and name == "return_gap":
            continue
        health = _health_from_thresholds(val, warn=warn, crit=crit, compare=cmp)
        out.append(
            MonitoringMetric(
                metric_id=build_metric_id(
                    strategy_code=strategy_code,
                    category="PERFORMANCE",
                    name=name,
                    collected_at=collected_at,
                ),
                strategy_code=strategy_code,
                category="PERFORMANCE",
                name=name,
                value=val,
                health=health,
                collected_at=collected_at,
                session_id=session_id,
            )
        )
    if not out and merged:
        out.append(
            MonitoringMetric(
                metric_id=build_metric_id(
                    strategy_code=strategy_code,
                    category="PERFORMANCE",
                    name="heartbeat",
                    collected_at=collected_at,
                ),
                strategy_code=strategy_code,
                category="PERFORMANCE",
                name="heartbeat",
                value=1.0,
                health="HEALTHY",
                collected_at=collected_at,
                session_id=session_id,
            )
        )
    return out


__all__ = ["collect_performance"]
