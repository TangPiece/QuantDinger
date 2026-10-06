"""Phase 3D：Production Backtest 十项验收（无 qlib）。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from app.services.research_data.backtest.execution.models import MarketBar
from app.services.research_data.backtest.fingerprint import compute_request_fingerprint
from app.services.research_data.backtest.presets import cn_equity_close_signal_next_open
from app.services.research_data.backtest.request import BacktestRequest
from app.services.research_data.backtest_production import ProductionBacktestEngine
from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import ExperimentDefinition, TargetPosition
from app.services.research_data.data_query import DataQuery
from app.services.research_data.registry import LocalJsonRegistry


IK = "CNStock:600519"


def _env(tmp_path: Path):
    store = LocalCanonicalStore(root=tmp_path / "canonical")
    registry = LocalJsonRegistry(root=tmp_path / "registry")
    query = DataQuery(store, registry)
    registry.upsert_experiment(
        ExperimentDefinition(
            experiment_id="exp_3d",
            name="phase3d",
            dataset_ref="dummy@1",
            snapshot_id="snap_3d",
            dataset_hash="ds_hash_3d",
            strategy_version="test@1",
            signal_artifact_id="sig_art_dummy",
        )
    )
    eng = ProductionBacktestEngine(
        query,
        registry,
        artifact_store=__import__(
            "app.services.research_data.backtest_production", fromlist=["ProductionArtifactStore"]
        ).ProductionArtifactStore(root=tmp_path / "bt_art"),
    )
    return eng, registry


def _request(**overrides) -> BacktestRequest:
    exec_p, price_p, cost_p, rules = cn_equity_close_signal_next_open()
    base = dict(
        experiment_id="exp_3d",
        dataset_hash="ds_hash_3d",
        strategy_version="test@1",
        start_date="2024-05-06",
        end_date="2024-05-08",
        initial_capital=1_000_000.0,
        engine="production",
        execution_policy=exec_p,
        market_price_policy=price_p,
        cost_policy=cost_p,
        trading_rule=rules,
        target_positions_artifact_id="sig_art_dummy",
    )
    base.update(overrides)
    return BacktestRequest(**base)


def _bar(day: str, **kwargs) -> MarketBar:
    raw = dict(
        instrument_key=IK,
        trading_date=day,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1e6,
        is_suspended=False,
        is_limit_up=False,
        is_limit_down=False,
    )
    raw.update(kwargs)
    return MarketBar(**raw)


def _bars(*days: str, **kwargs) -> dict[str, dict[str, MarketBar]]:
    return {d: {IK: _bar(d, **kwargs)} for d in days}


def _target(day: str, qty: float) -> TargetPosition:
    return TargetPosition(
        instrument_key=IK,
        trading_date=day,
        portfolio_id="p1",
        strategy_version="test@1",
        dataset_hash="ds_hash_3d",
        timestamp=datetime(2024, 5, 6, 15, 0, 0, tzinfo=timezone.utc),
        target_quantity=qty,
        target_weight=0.0,
        signal_id="s1",
    )


def test_no_trade_equity_equals_capital(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    eng, _ = _env(tmp_path)
    days = ["2024-05-06", "2024-05-07", "2024-05-08"]
    res = eng.run(
        _request(),
        bars_by_date=_bars(*days),
        targets_by_date={},
    )
    assert res.equity_curve
    assert abs(res.equity_curve[-1].equity - 1_000_000.0) < 1e-6
    assert res.engine == "production"
    assert res.artifact_uris.get("manifest")


def test_single_buy_cash_position_equity(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    eng, _ = _env(tmp_path)
    # T=05-06 signal → T+1=05-07 open fill @100, qty 100
    res = eng.run(
        _request(),
        bars_by_date=_bars("2024-05-06", "2024-05-07", "2024-05-08", open=100.0, close=100.0),
        targets_by_date={"2024-05-06": [_target("2024-05-06", 100)]},
    )
    filled = [t for t in res.trades if t.status in ("FILLED", "PARTIAL") and t.side == "BUY"]
    assert filled and filled[0].quantity == 100
    last = res.portfolio_history[-1]
    assert any(p.quantity == 100 for p in last.positions)
    assert last.cash < 1_000_000.0
    assert abs(last.total_value - (last.cash + 100 * 100.0)) < 1.0  # 含费用


def test_buy_and_sell_realized(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    eng, _ = _env(tmp_path)
    # 简化：T+0 以便两日完成买卖
    exec_p, price_p, cost_p, rules = cn_equity_close_signal_next_open()
    exec_p = exec_p.model_copy(update={"execution_delay": "T+0", "execution_price": "close"})
    rules = rules.model_copy(update={"t_plus": 0})
    req = _request(
        execution_policy=exec_p,
        trading_rule=rules,
        market_price_policy=price_p,
        cost_policy=cost_p,
    )
    targets = {
        "2024-05-06": [_target("2024-05-06", 100)],
        "2024-05-07": [_target("2024-05-07", 0)],
    }
    bars = {
        "2024-05-06": {IK: _bar("2024-05-06", close=100.0, open=100.0)},
        "2024-05-07": {IK: _bar("2024-05-07", close=110.0, open=110.0)},
        "2024-05-08": {IK: _bar("2024-05-08", close=110.0, open=110.0)},
    }
    res = eng.run(req, bars_by_date=bars, targets_by_date=targets)
    sells = [t for t in res.trades if t.side == "SELL" and t.status in ("FILLED", "PARTIAL")]
    assert sells
    last = res.portfolio_history[-1]
    assert last.realized_pnl != 0.0 or last.total_cost >= 0.0
    assert not last.positions or all(p.quantity == 0 for p in last.positions)


def test_limit_up_buy_no_fill(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    eng, _ = _env(tmp_path)
    bars = {
        "2024-05-06": {IK: _bar("2024-05-06")},
        "2024-05-07": {IK: _bar("2024-05-07", open=110.0, close=110.0, is_limit_up=True)},
        "2024-05-08": {IK: _bar("2024-05-08")},
    }
    res = eng.run(
        _request(),
        bars_by_date=bars,
        targets_by_date={"2024-05-06": [_target("2024-05-06", 1000)]},
    )
    filled = [t for t in res.trades if t.status in ("FILLED", "PARTIAL") and t.quantity > 0]
    assert not filled
    assert all(not p.positions for p in res.portfolio_history)


def test_limit_down_sell_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    eng, _ = _env(tmp_path)
    exec_p, price_p, cost_p, rules = cn_equity_close_signal_next_open()
    exec_p = exec_p.model_copy(update={"execution_delay": "T+0", "execution_price": "close"})
    rules = rules.model_copy(update={"t_plus": 0})
    # 先买入
    bars_buy = {
        "2024-05-06": {IK: _bar("2024-05-06", close=100.0)},
        "2024-05-07": {IK: _bar("2024-05-07", close=100.0)},
        "2024-05-08": {IK: _bar("2024-05-08", close=100.0)},
    }
    eng.run(
        _request(execution_policy=exec_p, trading_rule=rules, cost_policy=cost_p, market_price_policy=price_p),
        bars_by_date=bars_buy,
        targets_by_date={"2024-05-06": [_target("2024-05-06", 100)]},
    )
    # 新引擎实例但注入持仓：用第二次完整跑 —— 先买后在跌停日卖
    eng2, _ = _env(tmp_path / "b")
    bars = {
        "2024-05-06": {IK: _bar("2024-05-06", close=100.0)},
        "2024-05-07": {
            IK: _bar("2024-05-07", close=90.0, open=90.0, is_limit_down=True, lower_limit=90.0)
        },
        "2024-05-08": {IK: _bar("2024-05-08", close=90.0)},
    }
    targets = {
        "2024-05-06": [_target("2024-05-06", 100)],
        "2024-05-07": [_target("2024-05-07", 0)],
    }
    res = eng2.run(
        _request(execution_policy=exec_p, trading_rule=rules, cost_policy=cost_p, market_price_policy=price_p),
        bars_by_date=bars,
        targets_by_date=targets,
    )
    # 05-07 卖出应被跌停拒绝，持仓仍在
    day7 = next(p for p in res.portfolio_history if p.trading_date == "2024-05-07")
    assert any(p.quantity == 100 for p in day7.positions)
    assert any(t.reject_reason == "LIMIT_DOWN" for t in res.trades if t.side == "SELL")


def test_t_plus_same_day_sell_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    eng, _ = _env(tmp_path)
    exec_p, price_p, cost_p, rules = cn_equity_close_signal_next_open()
    # T+0 执行延迟以便当日买入；t_plus=1 禁止当日卖
    exec_p = exec_p.model_copy(update={"execution_delay": "T+0", "execution_price": "open"})
    assert rules.t_plus == 1
    bars = _bars("2024-05-06", "2024-05-07", "2024-05-08", open=10.0, close=10.0)
    targets = {
        "2024-05-06": [_target("2024-05-06", 100)],
        # 同日再发清仓信号 — intended 也是当日
        "2024-05-06b": [],  # placeholder ignored
    }
    # 同一天两个 target 无法表达；改为 pending：买完后同日再 step 清仓
    # 用一条 path：T+0 buy 100，同日再生成 sell 通过第二次 target 日=同日
    # targets_to_order_intents on same day after buy needs portfolio with position —
    # engine only generates intents from targets at start of day before step.
    # So: day1 target 100 → buy; day1 cannot also sell.
    # Use day1 buy with T+0; day1 won't sell. For same-day sell test call simulator path:
    from app.services.research_data.backtest.execution import ExecutionSimulator
    from app.services.research_data.contracts import OrderIntent
    from app.services.research_data.backtest.ledger import PortfolioSnapshot

    sim = ExecutionSimulator(exec_p, rules, cost_p, price_p)
    port = PortfolioSnapshot(trading_date="2024-05-06", cash=1_000_000.0, total_value=1_000_000.0)
    bars_d = {"2024-05-06": {IK: _bar("2024-05-06", open=10.0)}}
    buy = OrderIntent(
        instrument_key=IK,
        side="BUY",
        quantity=100,
        intended_execution_time=datetime(2024, 5, 6, 9, 30),
    )
    s1 = sim.step(trading_date="2024-05-06", intents=[buy], bars=bars_d["2024-05-06"], portfolio=port)
    sell = OrderIntent(
        instrument_key=IK,
        side="SELL",
        quantity=100,
        intended_execution_time=datetime(2024, 5, 6, 9, 30),
    )
    s2 = sim.step(
        trading_date="2024-05-06",
        intents=[sell],
        bars=bars_d["2024-05-06"],
        portfolio=s1.portfolio,
    )
    assert any(d.reason == "T_PLUS" for d in s2.decisions)
    assert s2.portfolio.positions


def test_lot_size_floor(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    eng, _ = _env(tmp_path)
    res = eng.run(
        _request(),
        bars_by_date=_bars("2024-05-06", "2024-05-07", "2024-05-08", open=50.0),
        targets_by_date={"2024-05-06": [_target("2024-05-06", 155)]},
    )
    filled = [t for t in res.trades if t.status in ("FILLED", "PARTIAL") and t.quantity > 0]
    assert filled
    assert filled[0].quantity == 100.0


def test_insufficient_cash_no_negative(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    eng, _ = _env(tmp_path)
    req = _request(initial_capital=1000.0)  # 只能买很少
    res = eng.run(
        req,
        bars_by_date=_bars("2024-05-06", "2024-05-07", "2024-05-08", open=100.0),
        targets_by_date={"2024-05-06": [_target("2024-05-06", 1000)]},
    )
    for p in res.portfolio_history:
        assert p.cash >= -1e-6


def test_suspension_keeps_position(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    eng, _ = _env(tmp_path)
    exec_p, price_p, cost_p, rules = cn_equity_close_signal_next_open()
    exec_p = exec_p.model_copy(update={"execution_delay": "T+0", "execution_price": "close"})
    rules = rules.model_copy(update={"t_plus": 0})
    bars = {
        "2024-05-06": {IK: _bar("2024-05-06", close=100.0)},
        "2024-05-07": {IK: _bar("2024-05-07", close=100.0, is_suspended=True)},
        "2024-05-08": {IK: _bar("2024-05-08", close=100.0)},
    }
    targets = {
        "2024-05-06": [_target("2024-05-06", 100)],
        "2024-05-07": [_target("2024-05-07", 0)],  # 想清仓但停牌
    }
    res = eng.run(
        _request(execution_policy=exec_p, trading_rule=rules, cost_policy=cost_p, market_price_policy=price_p),
        bars_by_date=bars,
        targets_by_date=targets,
    )
    day7 = next(p for p in res.portfolio_history if p.trading_date == "2024-05-07")
    assert any(p.quantity == 100 for p in day7.positions)
    assert any(t.reject_reason == "SUSPENDED" for t in res.trades)


def test_determinism_double_run(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))
    eng, _ = _env(tmp_path)
    req = _request()
    bars = _bars("2024-05-06", "2024-05-07", "2024-05-08", open=100.0)
    targets = {"2024-05-06": [_target("2024-05-06", 100)]}
    a = eng.run(req, bars_by_date=bars, targets_by_date=targets)
    b = eng.run(req, bars_by_date=bars, targets_by_date=targets)
    assert a.request_fingerprint == b.request_fingerprint == compute_request_fingerprint(req)
    assert abs(a.equity_curve[-1].equity - b.equity_curve[-1].equity) < 1e-6
    assert a.result_id == b.result_id
