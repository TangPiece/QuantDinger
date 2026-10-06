"""市场级政策预设：Simulator 只读 TradingRule 字段，无 if market==CN 分支。"""

from __future__ import annotations

from app.services.research_data.backtest.policy import (
    BacktestMarketPricePolicy,
    CostPolicy,
    ExecutionPolicy,
    TradingRule,
)
from app.services.research_data.backtest.presets import cn_equity_close_signal_next_open


def cn_a_share_execution_bundle() -> tuple[
    ExecutionPolicy, BacktestMarketPricePolicy, CostPolicy, TradingRule
]:
    """A 股：T+1 开盘、整手 floor、涨跌停、现金约束（复用 3A preset）。"""
    return cn_equity_close_signal_next_open()


def us_equity_t0_close() -> tuple[
    ExecutionPolicy, BacktestMarketPricePolicy, CostPolicy, TradingRule
]:
    """美股研究 stub：T+0 收盘、lot=1、可碎股。"""
    execution = ExecutionPolicy(
        signal_time_rule="close_of_signal_day",
        execution_delay="T+0",
        execution_price="close",
        execution_mode="market",
        timezone="America/New_York",
    )
    price = BacktestMarketPricePolicy(
        adjustment="none",
        return_type="price",
        reference_price="close",
    )
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
        market_calendar_id="US_NYSE",
        suspension_mode="skip",
        lot_rounding="floor",
        enforce_cash=True,
    )
    return execution, price, cost, rules


def hk_equity_t0_close() -> tuple[
    ExecutionPolicy, BacktestMarketPricePolicy, CostPolicy, TradingRule
]:
    """港股研究 stub：T+0 收盘；lot_size 可配（默认 100）。"""
    execution = ExecutionPolicy(
        signal_time_rule="close_of_signal_day",
        execution_delay="T+0",
        execution_price="close",
        execution_mode="market",
        timezone="Asia/Hong_Kong",
    )
    price = BacktestMarketPricePolicy(
        adjustment="none",
        return_type="price",
        reference_price="close",
    )
    cost = CostPolicy(
        commission_rate=0.0003,
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
        market_calendar_id="HK_HKEX",
        suspension_mode="skip",
        lot_rounding="floor",
        enforce_cash=True,
    )
    return execution, price, cost, rules
