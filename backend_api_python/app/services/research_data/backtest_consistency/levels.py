"""Level 0–5 政策工厂：逐步叠加成本与交易限制。"""

from __future__ import annotations

from app.services.research_data.backtest.policy import (
    BacktestMarketPricePolicy,
    CostPolicy,
    ExecutionPolicy,
    TradingRule,
)

from .models import ConsistencyLevel

# 相邻层归因分量映射：从 prev → curr 的增量归因到哪个 component
LEVEL_STEP_COMPONENT: dict[ConsistencyLevel, str] = {
    "L1": "commission",
    "L2": "slippage",
    "L3": "t_plus",
    "L4": "lot",
    "L5": "limit",  # L5 汇总限制类；细项由 reject reason 再拆
}

LEVEL_ORDER: list[ConsistencyLevel] = ["L0", "L1", "L2", "L3", "L4", "L5"]


def policies_for_level(
    level: ConsistencyLevel,
) -> tuple[ExecutionPolicy, BacktestMarketPricePolicy, CostPolicy, TradingRule]:
    """返回指定 Level 的完整四元组政策。

    L0 为理想环境；之后每层在前一层上叠加约束。
    """
    # --- L0 Ideal ---
    execution = ExecutionPolicy(
        signal_time_rule="close_of_signal_day",
        execution_delay="T+0",
        execution_price="close",
        execution_mode="market",
        timezone="Asia/Shanghai",
    )
    price = BacktestMarketPricePolicy(
        adjustment="none",
        return_type="price",
        reference_price="close",
        corporate_action_mode="ignore",
    )
    cost = CostPolicy(
        commission_rate=0.0,
        stamp_tax_rate=0.0,
        transfer_fee_rate=0.0,
        slippage_bps=0.0,
        minimum_commission=0.0,
        currency="CNY",
    )
    rules = TradingRule(
        lot_size=1,
        tick_size=0.01,
        t_plus=0,
        limit_up_down=False,
        limit_up_down_pct=None,
        short_allowed=False,
        fractional_shares=True,
        market_calendar_id="generic",
        suspension_mode="skip",
        lot_rounding="floor",
        enforce_cash=False,
    )

    if level == "L0":
        return execution, price, cost, rules

    # L1：手续费
    cost = cost.model_copy(
        update={
            "commission_rate": 0.0003,
            "minimum_commission": 5.0,
        }
    )
    if level == "L1":
        return execution, price, cost, rules

    # L2：滑点
    cost = cost.model_copy(update={"slippage_bps": 5.0})
    if level == "L2":
        return execution, price, cost, rules

    # L3：T+1 开盘执行
    execution = execution.model_copy(
        update={"execution_delay": "T+1", "execution_price": "open"}
    )
    price = price.model_copy(update={"reference_price": "open"})
    rules = rules.model_copy(update={"t_plus": 1})
    if level == "L3":
        return execution, price, cost, rules

    # L4：整手
    rules = rules.model_copy(
        update={
            "lot_size": 100,
            "fractional_shares": False,
            "lot_rounding": "floor",
        }
    )
    if level == "L4":
        return execution, price, cost, rules

    # L5：真实限制
    rules = rules.model_copy(
        update={
            "limit_up_down": True,
            "limit_up_down_pct": 0.1,
            "enforce_cash": True,
            "suspension_mode": "skip",
            "market_calendar_id": "CN_SSE_SZSE",
        }
    )
    cost = cost.model_copy(update={"stamp_tax_rate": 0.001})
    return execution, price, cost, rules
