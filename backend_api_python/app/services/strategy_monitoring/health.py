"""Phase 8F：StrategyHealthEngine — 优先级取最差，禁止加权平均。"""

from __future__ import annotations

from collections import defaultdict

from .protocol import (
    DimensionHealth,
    HealthStatus,
    MetricCategory,
    MonitoringMetric,
    StrategyHealth,
)

# 数值越大越差（WORST-priority）
_RANK: dict[HealthStatus, int] = {
    "UNKNOWN": 0,
    "HEALTHY": 1,
    "WARNING": 2,
    "DEGRADED": 3,
    "CRITICAL": 4,
    "HALTED": 5,
}

_HARD_CRITICAL_CATEGORIES: frozenset[MetricCategory] = frozenset(
    {"RECONCILIATION", "RISK", "MARKET_DATA"}
)


def _worst(a: HealthStatus, b: HealthStatus) -> HealthStatus:
    return a if _RANK[a] >= _RANK[b] else b


def dimension_health_from_metrics(metrics: list[MonitoringMetric]) -> dict[MetricCategory, HealthStatus]:
    """按分类聚合：取该维最差 metric.health。"""
    by_cat: dict[MetricCategory, HealthStatus] = {}
    grouped: dict[MetricCategory, list[MonitoringMetric]] = defaultdict(list)
    for m in metrics:
        grouped[m.category].append(m)
    for cat, items in grouped.items():
        status: HealthStatus = "UNKNOWN"
        for m in items:
            status = _worst(status, m.health)
        by_cat[cat] = status
    return by_cat


def aggregate_overall(dimension_map: dict[MetricCategory, HealthStatus]) -> HealthStatus:
    """WORST-priority + 硬规则（非加权）。"""
    overall: HealthStatus = "UNKNOWN"
    for st in dimension_map.values():
        overall = _worst(overall, st)

    any_critical = any(st == "CRITICAL" for st in dimension_map.values())
    if any_critical:
        overall = _worst(overall, "DEGRADED")

    for cat in _HARD_CRITICAL_CATEGORIES:
        if dimension_map.get(cat) == "CRITICAL":
            overall = _worst(overall, "CRITICAL")

    if dimension_map.get("RECONCILIATION") == "CRITICAL":
        overall = _worst(overall, "CRITICAL")

    return overall


def build_strategy_health(
    *,
    snapshot_id: str,
    strategy_code: str,
    metrics: list[MonitoringMetric],
    policy_id: str,
    policy_version: str,
    policy_content_hash: str,
    evaluated_at: str,
    session_id: str = "",
) -> StrategyHealth:
    dim_map = dimension_health_from_metrics(metrics)
    overall = aggregate_overall(dim_map)
    dimensions: list[DimensionHealth] = []
    grouped: dict[MetricCategory, list[MonitoringMetric]] = defaultdict(list)
    for m in metrics:
        grouped[m.category].append(m)
    for cat in sorted(dim_map.keys(), key=lambda c: c):
        st = dim_map[cat]
        dimensions.append(
            DimensionHealth(
                category=cat,
                status=st,
                summary=f"{cat}={st}",
                metric_count=len(grouped.get(cat, [])),
            )
        )
    return StrategyHealth(
        snapshot_id=snapshot_id,
        strategy_code=strategy_code,
        overall=overall,
        dimensions=dimensions,
        policy_id=policy_id,
        policy_version=policy_version,
        policy_content_hash=policy_content_hash,
        evaluated_at=evaluated_at,
        session_id=session_id,
    )


__all__ = [
    "aggregate_overall",
    "build_strategy_health",
    "dimension_health_from_metrics",
]
