"""常用政策预设（可表达 A 股 T+1 等，不执行回测）。"""

from __future__ import annotations

from .policy import (
    BacktestMarketPricePolicy,
    CostPolicy,
    ExecutionPolicy,
    TradingRule,
)


def cn_equity_close_signal_next_open() -> tuple[
    ExecutionPolicy, BacktestMarketPricePolicy, CostPolicy, TradingRule
]:
    """A 股日频：T 日收盘信号 → T+1 开盘执行；100 股整手、T+1、无空、涨跌停。"""
    execution = ExecutionPolicy(
        signal_time_rule="close_of_signal_day",
        execution_delay="T+1",
        execution_price="open",
        execution_mode="market",
        timezone="Asia/Shanghai",
    )
    price = BacktestMarketPricePolicy(
        adjustment="post",
        return_type="price",
        reference_price="open",
        corporate_action_mode="split_only",
    )
    cost = CostPolicy(
        commission_rate=0.0003,
        stamp_tax_rate=0.001,
        transfer_fee_rate=0.0,
        slippage_bps=5.0,
        minimum_commission=5.0,
        currency="CNY",
    )
    rules = TradingRule(
        lot_size=100,
        tick_size=0.01,
        t_plus=1,
        limit_up_down=True,
        limit_up_down_pct=0.1,
        short_allowed=False,
        fractional_shares=False,
        market_calendar_id="CN_SSE_SZSE",
        suspension_mode="skip",
    )
    return execution, price, cost, rules


def research_qlib_relaxed() -> tuple[
    ExecutionPolicy, BacktestMarketPricePolicy, CostPolicy, TradingRule
]:
    """Qlib Research 简化规则（3B 默认）；仍走同一 Contract。"""
    execution = ExecutionPolicy(
        signal_time_rule="close_of_signal_day",
        execution_delay="T+0",
        execution_price="close",
        execution_mode="market",
    )
    price = BacktestMarketPricePolicy(
        adjustment="none",
        return_type="price",
        reference_price="close",
    )
    cost = CostPolicy()
    rules = TradingRule(
        lot_size=1,
        t_plus=0,
        limit_up_down=False,
        short_allowed=True,
        fractional_shares=True,
        market_calendar_id="generic",
    )
    return execution, price, cost, rules
