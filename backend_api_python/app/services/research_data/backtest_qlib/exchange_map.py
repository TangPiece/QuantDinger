"""CostPolicy / TradingRule / ExecutionPolicy → Qlib Exchange kwargs。

3B 仅做简化映射；完整 A 股 T+1 / 涨跌停撮合留给 3C/3D。
"""

from __future__ import annotations

from typing import Any

from app.services.research_data.backtest.policy import (
    BacktestMarketPricePolicy,
    CostPolicy,
    ExecutionPolicy,
    TradingRule,
)
from app.services.research_data.backtest.request import BacktestRequest


def map_deal_price(
    execution: ExecutionPolicy,
    market_price: BacktestMarketPricePolicy,
) -> str:
    """映射成交价字段；优先 execution_price，其次 reference_price。"""
    price = execution.execution_price or market_price.reference_price or "close"
    if price in ("open", "close", "vwap"):
        return price
    return "close"


def map_exchange_kwargs(request: BacktestRequest) -> dict[str, Any]:
    """将 Domain 政策转为 ``qlib.backtest.backtest(..., exchange_kwargs=...)``。

    - open_cost / close_cost：佣金 + 印花税简化（卖出侧叠加 stamp）
    - trade_unit：lot_size；fractional / lot_size=1 时置 None 关闭整手
    - limit_threshold：开启涨跌停时用 pct，否则 None
    - account 不在此返回（由 backtest account= 传入）
    """
    cost = request.cost_policy
    rules = request.trading_rule
    execution = request.execution_policy
    market = request.market_price_policy

    commission = float(cost.commission_rate or 0.0)
    stamp = float(cost.stamp_tax_rate or 0.0)
    transfer = float(cost.transfer_fee_rate or 0.0)
    # 滑点 bps → 近似加到双边成本（研究简化）
    slip = float(cost.slippage_bps or 0.0) / 10000.0

    open_cost = commission + transfer + slip
    close_cost = commission + stamp + transfer + slip

    if rules.fractional_shares or int(rules.lot_size or 1) <= 1:
        trade_unit = None
    else:
        trade_unit = int(rules.lot_size)

    if rules.limit_up_down and rules.limit_up_down_pct is not None:
        limit_threshold: float | None = float(rules.limit_up_down_pct)
    else:
        limit_threshold = None

    return {
        "freq": "day",
        "deal_price": map_deal_price(execution, market),
        "open_cost": open_cost,
        "close_cost": close_cost,
        "min_cost": float(cost.minimum_commission or 0.0),
        "trade_unit": trade_unit,
        "limit_threshold": limit_threshold,
        "codes": "all",
    }
