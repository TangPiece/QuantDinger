"""Phase 8F：Dashboard 查询聚合（无 Flask 路由）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .bridges.bridge_from_feedback import drift_view
from .bridges.reconciliation import reconciliation_view
from .bridges.risk_policy import risk_view
from .protocol import DashboardSnapshot, MonitoringMetric, StrategyAlert, StrategyHealth


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metrics_by_name(metrics: list[MonitoringMetric], category: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for m in metrics:
        if m.category == category:
            out[m.name] = float(m.value)
    return out


def build_dashboard_snapshot(
    *,
    strategy_code: str,
    health: StrategyHealth,
    metrics: list[MonitoringMetric],
    alerts: list[StrategyAlert],
    feedback_scalars: dict[str, float] | None = None,
    recon_section: dict[str, Any] | None = None,
) -> DashboardSnapshot:
    perf = _metrics_by_name(metrics, "PERFORMANCE")
    risk_m = _metrics_by_name(metrics, "RISK")
    exec_m = _metrics_by_name(metrics, "EXECUTION")
    active = [a for a in alerts if a.status not in ("RESOLVED",)]
    return DashboardSnapshot(
        strategy_code=strategy_code,
        health=health,
        active_alerts=active,
        recent_metrics=metrics,
        performance=perf,
        risk=risk_view(risk_m),
        execution=exec_m,
        drift=drift_view(feedback_scalars or {}),
        reconciliation=reconciliation_view(recon_section or {}),
        generated_at=_now(),
    )


__all__ = ["build_dashboard_snapshot"]
