"""Phase 8F：Reconciliation 维度（只读 findings 摘要）。"""

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


def _health_from_severity(sev: str, crit_count: float) -> HealthStatus:
    s = str(sev or "").strip().upper()
    if s == "CRITICAL" or crit_count >= 1.0:
        return "CRITICAL"
    if s == "WARNING":
        return "WARNING"
    if crit_count > 0:
        return "CRITICAL"
    return "HEALTHY"


def collect_reconciliation(
    strategy_code: str,
    *,
    collected_at: str,
    session_id: str,
    section: Mapping[str, Any],
    recon_inject: Mapping[str, Any] | None,
) -> list[MonitoringMetric]:
    merged = {**(recon_inject or {}), **dict(section)}
    crit = _f(merged, "critical_finding_count", _f(merged, "critical_findings"))
    sev = str(merged.get("severity") or merged.get("overall_severity") or "")
    health = _health_from_severity(sev, crit)
    return [
        MonitoringMetric(
            metric_id=build_metric_id(
                strategy_code=strategy_code,
                category="RECONCILIATION",
                name="critical_finding_count",
                collected_at=collected_at,
            ),
            strategy_code=strategy_code,
            category="RECONCILIATION",
            name="critical_finding_count",
            value=crit,
            health=health,
            collected_at=collected_at,
            session_id=session_id,
            labels={"severity": sev or "OK"},
        )
    ]


__all__ = ["collect_reconciliation"]
