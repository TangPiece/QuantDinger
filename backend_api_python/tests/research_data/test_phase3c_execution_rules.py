"""Phase 3C：Trading Cost & Execution Rules（无 qlib）。"""

from __future__ import annotations

from datetime import date, datetime

from app.services.research_data.backtest.execution import (
    REASON_EXECUTION_DELAY,
    REASON_LIMIT_DOWN,
    REASON_LIMIT_UP,
    REASON_LOT_SIZE_FLOOR,
    REASON_SUSPENDED,
    ExecutionSimulator,
    MarketBar,
    adjust_lot_quantity,
    compute_cost_breakdown,
    decide_execution,
    resolve_execution_date,
    run_pipeline,
)
from app.services.research_data.backtest.ledger import PortfolioSnapshot, PositionSnapshot
from app.services.research_data.backtest.presets import cn_equity_close_signal_next_open
from app.services.research_data.contracts import OrderIntent, TargetPosition


def _cn_bundle():
    return cn_equity_close_signal_next_open()


def _bar(
    ik: str = "CNStock:600519",
    trading_date: str = "2024-05-07",
    **kwargs,
) -> MarketBar:
    base = dict(
        instrument_key=ik,
        trading_date=trading_date,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1_000_000.0,
        is_suspended=False,
        is_limit_up=False,
        is_limit_down=False,
    )
    base.update(kwargs)
    return MarketBar(**base)


def _target(
    *,
    trading_date: str = "2024-05-06",
    weight: float = 0.5,
    quantity: float | None = None,
    ik: str = "CNStock:600519",
) -> TargetPosition:
    return TargetPosition(
        instrument_key=ik,
        trading_date=trading_date,
        portfolio_id="p1",
        strategy_version="test@1",
        dataset_hash="ds",
        timestamp=datetime(2024, 5, 6, 15, 0, 0),
        target_weight=weight,
        target_quantity=quantity,
        signal_id="sig1",
    )


def test_t_plus_one_no_fill_on_signal_day():
    """T 日信号 → T 日不能成交；T+1 可执行。"""
    exec_p, price_p, cost_p, rules = _cn_bundle()
    # 显式日历：周一信号 → 周二执行
    cal = [date(2024, 5, 6), date(2024, 5, 7), date(2024, 5, 8)]
    exec_day = resolve_execution_date(
        "2024-05-06", "T+1", market_calendar_id="CN_SSE_SZSE", calendar=cal
    )
    assert exec_day == date(2024, 5, 7)

    portfolio = PortfolioSnapshot(trading_date="2024-05-06", cash=1_000_000.0, total_value=1_000_000.0)
    bars_t = {"CNStock:600519": _bar(trading_date="2024-05-06")}
    bars_t1 = {"CNStock:600519": _bar(trading_date="2024-05-07", open=100.0)}

    # 指定目标股数，避免权重换算干扰
    targets = [_target(trading_date="2024-05-06", quantity=100.0, weight=None)]
    # weight None 可能不合法 — 用 weight=0 并用 quantity
    targets = [
        TargetPosition(
            instrument_key="CNStock:600519",
            trading_date="2024-05-06",
            portfolio_id="p1",
            strategy_version="test@1",
            dataset_hash="ds",
            timestamp=datetime(2024, 5, 6, 15, 0, 0),
            target_weight=0.0,
            target_quantity=100.0,
            signal_id="sig1",
        )
    ]

    pipe_t = run_pipeline(
        targets=targets,
        portfolio=portfolio,
        bars=bars_t,
        execution_policy=exec_p,
        trading_rule=rules,
        cost_policy=cost_p,
        market_price_policy=price_p,
        execution_date="2024-05-06",
        calendar=cal,
    )
    assert all(d.reason == REASON_EXECUTION_DELAY for d in pipe_t.decisions)
    assert all(t.status == "REJECTED" for t in pipe_t.trades)

    pipe_t1 = run_pipeline(
        targets=targets,
        portfolio=portfolio,
        bars=bars_t1,
        execution_policy=exec_p,
        trading_rule=rules,
        cost_policy=cost_p,
        market_price_policy=price_p,
        execution_date="2024-05-07",
        calendar=cal,
    )
    filled = [t for t in pipe_t1.trades if t.status in ("FILLED", "PARTIAL")]
    assert filled
    assert filled[0].quantity == 100.0


def test_lot_size_floor_155_to_100():
    """target=155, lot=100, floor → 100 + rejected 55。"""
    _, _, _, rules = _cn_bundle()
    assert rules.lot_rounding == "floor"
    adj = adjust_lot_quantity(155, rules)
    assert adj.executable_quantity == 100.0
    assert adj.rejected_quantity == 55.0
    assert adj.reason == REASON_LOT_SIZE_FLOOR

    decision = decide_execution(
        instrument_key="CNStock:600519",
        side="BUY",
        quantity=155,
        bar=_bar(),
        rule=rules,
        fill_price=100.0,
    )
    assert decision.executable
    assert decision.executable_quantity == 100.0
    assert decision.rejected_quantity == 55.0
    assert decision.reason == REASON_LOT_SIZE_FLOOR


def test_limit_up_blocks_buy():
    _, _, _, rules = _cn_bundle()
    bar = _bar(is_limit_up=True, open=110.0, close=110.0, upper_limit=110.0)
    d = decide_execution(
        instrument_key=bar.instrument_key,
        side="BUY",
        quantity=100,
        bar=bar,
        rule=rules,
        fill_price=110.0,
    )
    assert d.executable is False
    assert d.reason == REASON_LIMIT_UP


def test_limit_down_blocks_sell():
    _, _, _, rules = _cn_bundle()
    bar = _bar(is_limit_down=True, open=90.0, close=90.0, lower_limit=90.0)
    d = decide_execution(
        instrument_key=bar.instrument_key,
        side="SELL",
        quantity=100,
        bar=bar,
        rule=rules,
        sellable_quantity=100,
        fill_price=90.0,
    )
    assert d.executable is False
    assert d.reason == REASON_LIMIT_DOWN


def test_suspension_rejects_both_sides():
    _, _, _, rules = _cn_bundle()
    assert rules.suspension_mode == "skip"
    bar = _bar(is_suspended=True)
    for side in ("BUY", "SELL"):
        d = decide_execution(
            instrument_key=bar.instrument_key,
            side=side,
            quantity=100,
            bar=bar,
            rule=rules,
            sellable_quantity=100,
            fill_price=100.0,
        )
        assert d.executable is False
        assert d.reason == REASON_SUSPENDED


def test_cost_net_identity():
    exec_p, _, cost_p, _ = _cn_bundle()
    _ = exec_p
    buy = compute_cost_breakdown(
        side="BUY", quantity=100, executed_price=10.0, cost_policy=cost_p
    )
    # BUY: net_cash_delta = -(gross + total)
    assert abs(buy.net_cash_delta - (-(buy.gross_value + buy.total_cost))) < 1e-9
    assert abs(
        buy.total_cost
        - (buy.commission + buy.stamp_tax + buy.transfer_fee + buy.slippage + buy.other_fee)
    ) < 1e-9

    sell = compute_cost_breakdown(
        side="SELL", quantity=100, executed_price=10.0, cost_policy=cost_p
    )
    assert abs(sell.net_cash_delta - (sell.gross_value - sell.total_cost)) < 1e-9
    assert sell.stamp_tax > 0  # CN sell stamp


def test_full_pipeline_target_to_position():
    """Signal/Target → OrderIntent → Decision → Trade → Position。"""
    exec_p, price_p, cost_p, rules = _cn_bundle()
    cal = [date(2024, 5, 6), date(2024, 5, 7), date(2024, 5, 8)]
    portfolio = PortfolioSnapshot(
        trading_date="2024-05-06",
        cash=1_000_000.0,
        total_value=1_000_000.0,
        positions=[],
    )
    targets = [
        TargetPosition(
            instrument_key="CNStock:600519",
            trading_date="2024-05-06",
            portfolio_id="p1",
            strategy_version="topk@1",
            dataset_hash="ds",
            timestamp=datetime(2024, 5, 6, 15, 0, 0),
            target_quantity=200.0,
            target_weight=0.0,
            signal_id="s1",
        )
    ]
    bars = {
        "CNStock:600519": _bar(trading_date="2024-05-07", open=50.0, close=51.0),
    }
    result = run_pipeline(
        targets=targets,
        portfolio=portfolio,
        bars=bars,
        execution_policy=exec_p,
        trading_rule=rules,
        cost_policy=cost_p,
        market_price_policy=price_p,
        execution_date="2024-05-07",
        calendar=cal,
    )
    assert result.intents
    assert result.intents[0].side == "BUY"
    assert result.intents[0].quantity_delta == 200.0
    assert result.intents[0].intended_execution_time is not None
    assert result.intents[0].intended_execution_time.date() == date(2024, 5, 7)

    filled = [t for t in result.trades if t.status in ("FILLED", "PARTIAL")]
    assert filled
    assert filled[0].quantity == 200.0
    assert filled[0].commission >= 0
    assert result.portfolio.positions
    assert result.portfolio.positions[0].quantity == 200.0
    assert result.portfolio.cash < 1_000_000.0


def test_t_plus_inventory_blocks_same_day_sell():
    """当日买入不可当日卖出（TradingRule.t_plus=1）。"""
    exec_p, price_p, cost_p, rules = _cn_bundle()
    sim = ExecutionSimulator(exec_p, rules, cost_p, price_p)
    portfolio = PortfolioSnapshot(
        trading_date="2024-05-07",
        cash=1_000_000.0,
        total_value=1_000_000.0,
    )
    bars = {"CNStock:600519": _bar(trading_date="2024-05-07", open=10.0)}
    buy_intent = OrderIntent(
        instrument_key="CNStock:600519",
        side="BUY",
        quantity=100,
        trading_date="2024-05-07",
        intended_execution_time=datetime(2024, 5, 7, 9, 30),
    )
    step1 = sim.step(
        trading_date="2024-05-07",
        intents=[buy_intent],
        bars=bars,
        portfolio=portfolio,
    )
    assert step1.portfolio and step1.portfolio.positions

    sell_intent = OrderIntent(
        instrument_key="CNStock:600519",
        side="SELL",
        quantity=100,
        trading_date="2024-05-07",
        intended_execution_time=datetime(2024, 5, 7, 9, 30),
    )
    step2 = sim.step(
        trading_date="2024-05-07",
        intents=[sell_intent],
        bars=bars,
        portfolio=step1.portfolio,
    )
    assert any(d.reason == "T_PLUS" for d in step2.decisions)
    assert step2.portfolio.positions  # 仍持有
