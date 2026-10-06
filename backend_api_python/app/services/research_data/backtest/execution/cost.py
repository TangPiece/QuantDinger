"""CostPolicy → CostBreakdown（可审计拆账）。"""

from __future__ import annotations

from typing import Literal

from app.services.research_data.backtest.policy import CostPolicy

from .models import CostBreakdown


def compute_cost_breakdown(
    *,
    side: Literal["BUY", "SELL"],
    quantity: float,
    executed_price: float,
    cost_policy: CostPolicy,
) -> CostBreakdown:
    """计算单笔成交费用。

    - commission = max(gross * commission_rate, minimum_commission)（费率或最低佣金启用时）
    - stamp_tax：默认仅 SELL
    - transfer_fee：双边按 rate
    - slippage：gross * bps/10000
    - BUY: net_cash_delta = -(gross + total_cost)
    - SELL: net_cash_delta = +(gross - total_cost)
    """
    qty = abs(float(quantity))
    price = float(executed_price)
    gross = qty * price
    if qty <= 0 or price < 0:
        return CostBreakdown(gross_value=0.0, net_cash_delta=0.0)

    slip_rate = float(cost_policy.slippage_bps or 0.0) / 10000.0
    slippage = gross * slip_rate
    transfer = gross * float(cost_policy.transfer_fee_rate or 0.0)
    stamp = 0.0
    if side == "SELL":
        stamp = gross * float(cost_policy.stamp_tax_rate or 0.0)

    rate = float(cost_policy.commission_rate or 0.0)
    min_comm = float(cost_policy.minimum_commission or 0.0)
    if rate > 0.0 or min_comm > 0.0:
        commission = max(gross * rate, min_comm)
    else:
        commission = 0.0

    total = commission + stamp + transfer + slippage
    if side == "BUY":
        net = -(gross + total)
    else:
        net = gross - total

    return CostBreakdown(
        commission=commission,
        stamp_tax=stamp,
        transfer_fee=transfer,
        slippage=slippage,
        other_fee=0.0,
        total_cost=total,
        gross_value=gross,
        net_cash_delta=net,
    )
