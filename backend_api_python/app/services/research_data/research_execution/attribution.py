"""Gross / Net 双轨归因。"""

from __future__ import annotations

from typing import Sequence

from .protocol import (
    AttributionBreakdown,
    AttributionReport,
    DailyCostRow,
)


def build_attribution(
    *,
    initial_nav: float,
    gross_final_nav: float,
    net_final_nav: float,
    cost_rows: Sequence[DailyCostRow],
) -> AttributionReport:
    """用毛/净终值与累计费用桶解释收益差。

    ``unfilled_drag`` = (gross_nav - net_nav) - sum(costs)，即约束未成交残差
    （以 NAV 单位计，再换算为相对 initial_nav 的 return drag）。
    """
    start = float(initial_nav) if initial_nav > 0 else 1.0
    gross_ret = gross_final_nav / start - 1.0
    net_ret = net_final_nav / start - 1.0
    delta = gross_ret - net_ret

    commission = sum(float(r.commission) for r in cost_rows)
    stamp = sum(float(r.stamp_tax) for r in cost_rows)
    slip = sum(float(r.slippage) for r in cost_rows)
    transfer = sum(float(r.transfer_fee) for r in cost_rows)
    total_cost = commission + stamp + slip + transfer

    # 费用拖累 ≈ cost / initial_nav；未成交残差吃掉剩余 NAV 差
    nav_gap = float(gross_final_nav) - float(net_final_nav)
    unfilled_nav = max(0.0, nav_gap - total_cost)
    other_nav = nav_gap - total_cost - unfilled_nav  # 通常 ~0；负则并入 other

    def _drag(amount: float) -> float:
        return amount / start

    breakdown = AttributionBreakdown(
        commission_drag=_drag(commission),
        stamp_tax_drag=_drag(stamp),
        slippage_drag=_drag(slip),
        transfer_fee_drag=_drag(transfer),
        unfilled_drag=_drag(unfilled_nav),
        other=_drag(other_nav) if abs(other_nav) > 1e-12 else 0.0,
    )
    return AttributionReport(
        gross_total_return=gross_ret,
        net_total_return=net_ret,
        delta_return=delta,
        breakdown=breakdown,
        initial_nav=start,
        gross_final_nav=float(gross_final_nav),
        net_final_nav=float(net_final_nav),
        metadata={
            "total_cost_absolute": total_cost,
            "nav_gap": nav_gap,
        },
    )
