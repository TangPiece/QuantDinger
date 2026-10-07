"""Phase 7E：策略容量上限（participation / turnover / order size）。"""

from __future__ import annotations

from .protocol import CapacityLimit, OrderRiskContext


class CapacityReject(RuntimeError):
    pass


def check_capacity(
    cap: CapacityLimit,
    ctx: OrderRiskContext,
    *,
    daily_turnover_used: float = 0.0,
) -> tuple[bool, str]:
    qty = float(ctx.quantity)
    notional = float(ctx.notional)
    if cap.max_order_size > 0 and qty > cap.max_order_size:
        return False, "max_order_size"
    if cap.max_notional > 0 and notional > cap.max_notional:
        return False, "capacity_max_notional"
    if cap.max_daily_turnover > 0 and daily_turnover_used + notional > cap.max_daily_turnover:
        return False, "max_daily_turnover"
    # participation_rate 需外部 ADV；golden 仅校验字段存在
    if cap.max_participation_rate > 0 and ctx.metadata.get("participation_rate"):
        pr = float(ctx.metadata["participation_rate"])
        if pr > cap.max_participation_rate:
            return False, "max_participation_rate"
    return True, ""
