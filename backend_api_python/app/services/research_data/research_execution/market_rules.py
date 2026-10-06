"""MarketRule：按市场打包 CostPolicy + TradingRule（禁止引擎硬编码费率）。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.backtest.policy import (
    BacktestMarketPricePolicy,
    CostPolicy,
    ExecutionPolicy,
    TradingRule,
)
from app.services.research_data.backtest.presets import cn_equity_close_signal_next_open

from .protocol import MarketRuleId


def resolve_market_bundle(
    market_rule: MarketRuleId,
    *,
    research_fill_field: str = "open",
    research_delay_already_applied: bool = True,
    cost_policy_override: dict[str, Any] | None = None,
    trading_rule_override: dict[str, Any] | None = None,
) -> tuple[ExecutionPolicy, BacktestMarketPricePolicy, CostPolicy, TradingRule]:
    """解析市场规则包。

    research 层已完成信号→执行日映射时，3C ``execution_delay`` 固定 ``T+0``，
    避免二次延迟；成交价字段对齐 ResearchExecutionPolicy.fill_field。
    执行价 adjustment 强制 ``none``（不可用复权价当真成交）。
    """
    if market_rule == "CN_A":
        _exec, _price, cost, rules = cn_equity_close_signal_next_open()
    elif market_rule == "HK":
        cost = CostPolicy(
            commission_rate=0.0008,
            stamp_tax_rate=0.001,
            slippage_bps=5.0,
            minimum_commission=0.0,
            currency="HKD",
        )
        rules = TradingRule(
            lot_size=100,
            tick_size=0.01,
            t_plus=0,
            limit_up_down=False,
            short_allowed=False,
            fractional_shares=False,
            market_calendar_id="HKEX",
            lot_rounding="floor",
            enforce_cash=True,
        )
    elif market_rule == "US":
        cost = CostPolicy(
            commission_rate=0.0,
            stamp_tax_rate=0.0,
            slippage_bps=1.0,
            minimum_commission=0.0,
            currency="USD",
        )
        rules = TradingRule(
            lot_size=1,
            tick_size=0.01,
            t_plus=0,
            limit_up_down=False,
            short_allowed=True,
            fractional_shares=True,
            market_calendar_id="NYSE",
            lot_rounding="floor",
            enforce_cash=True,
        )
    else:
        raise ValueError(f"unsupported market_rule: {market_rule}")

    if cost_policy_override:
        cost = cost.model_copy(update=cost_policy_override)
    if trading_rule_override:
        rules = rules.model_copy(update=trading_rule_override)

    delay = "T+0" if research_delay_already_applied else "T+1"
    fill = research_fill_field if research_fill_field in ("open", "close", "vwap") else "open"
    execution = ExecutionPolicy(
        signal_time_rule="close_of_signal_day",
        execution_delay=delay,
        execution_price=fill,  # type: ignore[arg-type]
        execution_mode="market",
        timezone="Asia/Shanghai" if market_rule == "CN_A" else "UTC",
    )
    # 执行价：强制 none，与研究复权价分离
    price = BacktestMarketPricePolicy(
        adjustment="none",
        return_type="price",
        reference_price=fill if fill in ("open", "close", "vwap") else "close",  # type: ignore[arg-type]
        corporate_action_mode="ignore",
    )
    return execution, price, cost, rules


def fingerprint_policies(cost: CostPolicy, rules: TradingRule) -> dict[str, Any]:
    """进入 backtest_hash 的规范化策略指纹。"""
    return {
        "cost_policy": cost.model_dump(mode="json"),
        "trading_rule": rules.model_dump(mode="json"),
    }
