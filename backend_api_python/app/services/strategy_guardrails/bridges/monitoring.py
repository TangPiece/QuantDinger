"""Phase 8G：只读 8F StrategyMonitoringService。"""

from __future__ import annotations

from typing import Any


def load_monitoring_context(
    monitoring: Any | None,
    *,
    strategy_code: str,
) -> tuple[Any, list[Any]]:
    """返回 (health, alerts)；monitoring 缺失时空。"""
    if monitoring is None:
        return None, []
    health = None
    alerts: list[Any] = []
    try:
        health = monitoring.get_health(strategy_code)
    except Exception:
        pass
    try:
        alerts = monitoring.list_alerts(strategy_code)
    except Exception:
        alerts = []
    return health, alerts


__all__ = ["load_monitoring_context"]
