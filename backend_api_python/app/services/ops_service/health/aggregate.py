"""多组件健康聚合：任一 UNHEALTHY → 整体 UNHEALTHY；否则若存在 DEGRADED → DEGRADED。"""

from __future__ import annotations

from ..protocol import ComponentHealth, HealthStatus, TradingHealth


def aggregate_status(components: list[ComponentHealth]) -> HealthStatus:
    """聚合规则：有 UNHEALTHY 则 UNHEALTHY；否则有 DEGRADED 则 DEGRADED；全 HEALTHY 则 HEALTHY。"""
    if any(c.status == "UNHEALTHY" for c in components):
        return "UNHEALTHY"
    if any(c.status == "DEGRADED" for c in components):
        return "DEGRADED"
    return "HEALTHY"


def build_trading_health(components: list[ComponentHealth]) -> TradingHealth:
    """将命名组件写入 TradingHealth 并计算 overall。"""
    by_name = {c.name: c for c in components}
    health = TradingHealth(
        overall=aggregate_status(components),
        broker=by_name.get("broker", ComponentHealth(name="broker")),
        oms=by_name.get("oms", ComponentHealth(name="oms")),
        safety=by_name.get("safety", ComponentHealth(name="safety")),
        reconciliation=by_name.get(
            "reconciliation", ComponentHealth(name="reconciliation")
        ),
        market_data=by_name.get("market_data", ComponentHealth(name="market_data")),
        components=components,
    )
    return health
