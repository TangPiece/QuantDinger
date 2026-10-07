"""Phase 7E：Scale Level 档位与 entry/exit/rollback 指标评估（仅建议，不自动升档）。"""

from __future__ import annotations

from typing import Any, Mapping

from .protocol import ScaleCriteriaReport, ScaleLevel

# 档位 → 典型 env 与 caps 轮廓（金额由 resolver 与 env 叠加，非硬编码生产值）
_SCALE_PROFILES: dict[ScaleLevel, dict[str, float | int | str]] = {
    "L0_SHADOW": {
        "max_notional_per_order": 0.0,
        "max_notional_session": 0.0,
        "max_orders": 0,
        "environment": "SHADOW",
    },
    "L1_CONTROLLED": {
        "max_notional_per_order": 500.0,
        "max_notional_session": 1500.0,
        "max_orders": 1,
        "environment": "LIVE_CONTROLLED",
    },
    "L2_SMALL": {
        "max_notional_per_order": 2000.0,
        "max_notional_session": 6000.0,
        "max_orders": 3,
        "environment": "LIVE_CONTROLLED",
    },
    "L3_MEDIUM": {
        "max_notional_per_order": 10000.0,
        "max_notional_session": 30000.0,
        "max_orders": 10,
        "environment": "LIVE_CONTROLLED",
    },
    "L4_PRODUCTION": {
        "max_notional_per_order": 50000.0,
        "max_notional_session": 150000.0,
        "max_orders": 50,
        "environment": "LIVE",
    },
}

_LEVEL_ORDER: tuple[ScaleLevel, ...] = (
    "L0_SHADOW",
    "L1_CONTROLLED",
    "L2_SMALL",
    "L3_MEDIUM",
    "L4_PRODUCTION",
)


def scale_profile(level: ScaleLevel) -> dict[str, float | int | str]:
    return dict(_SCALE_PROFILES[level])


def next_level(current: ScaleLevel) -> ScaleLevel | None:
    try:
        idx = _LEVEL_ORDER.index(current)
    except ValueError:
        return None
    if idx + 1 >= len(_LEVEL_ORDER):
        return None
    return _LEVEL_ORDER[idx + 1]


def evaluate_scale_up_criteria(
    *,
    strategy_id: str,
    from_level: ScaleLevel,
    to_level: ScaleLevel,
    metrics: Mapping[str, Any] | None = None,
) -> ScaleCriteriaReport:
    """多指标报告；criteria_met 仅作参考，禁止单独 PnL 触发自动升档。"""
    m = dict(metrics or {})
    # 参考阈值（不足仍可由人工 approve）
    dd_ok = float(m.get("max_drawdown_pct", 999)) <= float(m.get("dd_limit_pct", 15))
    recon_ok = int(m.get("recon_critical_count", 0)) == 0
    reject_ok = int(m.get("consecutive_rejects", 0)) <= 2
    criteria_met = dd_ok and recon_ok and reject_ok
    return ScaleCriteriaReport(
        strategy_id=strategy_id,
        from_level=from_level,
        to_level=to_level,
        metrics=m,
        criteria_met=criteria_met,
        recommendation="MANUAL_APPROVAL_REQUIRED",
    )
