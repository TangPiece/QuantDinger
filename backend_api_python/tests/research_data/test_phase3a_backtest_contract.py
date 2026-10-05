"""Phase 3A：Backtest Contract 契约与预设（无 qlib）。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.research_data.backtest import (
    BACKTEST_CONTRACT_VERSION,
    BacktestMetrics,
    BacktestRequest,
    BacktestResult,
    CostPolicy,
    ExecutionPolicy,
    TradeRecord,
    cn_equity_close_signal_next_open,
    compute_request_fingerprint,
    research_qlib_relaxed,
)


def _sample_request(**overrides) -> BacktestRequest:
    exec_p, price_p, cost_p, rules = cn_equity_close_signal_next_open()
    base = dict(
        experiment_id="exp_test_001",
        dataset_hash="ds_hash_abc",
        strategy_version="topk@1",
        start_date="2024-01-01",
        end_date="2024-06-30",
        initial_capital=1_000_000.0,
        engine="production",
        execution_policy=exec_p,
        market_price_policy=price_p,
        cost_policy=cost_p,
        trading_rule=rules,
    )
    base.update(overrides)
    return BacktestRequest(**base)


def test_request_result_round_trip():
    req = _sample_request()
    fp = compute_request_fingerprint(req)
    assert fp
    assert req.contract_version == BACKTEST_CONTRACT_VERSION
    raw = req.model_dump(mode="json")
    req2 = BacktestRequest.model_validate(raw)
    assert compute_request_fingerprint(req2) == fp

    res = BacktestResult(
        result_id="res_1",
        request_fingerprint=fp,
        experiment_id=req.experiment_id,
        dataset_hash=req.dataset_hash,
        engine="production",
        contract_version=BACKTEST_CONTRACT_VERSION,
        metrics=BacktestMetrics(sharpe=1.2),
    )
    res2 = BacktestResult.model_validate(res.model_dump(mode="json"))
    assert res2.metrics.sharpe == 1.2


def test_cn_equity_preset_t_plus_lot_limit():
    exec_p, _, cost_p, rules = cn_equity_close_signal_next_open()
    assert exec_p.execution_delay == "T+1"
    assert exec_p.execution_price == "open"
    assert rules.lot_size == 100
    assert rules.t_plus == 1
    assert rules.short_allowed is False
    assert rules.limit_up_down is True
    assert rules.limit_up_down_pct == 0.1
    assert cost_p.slippage_bps == 5.0


def test_execution_and_cost_expressible():
    req = _sample_request(
        execution_policy=ExecutionPolicy(
            execution_delay="calendar_days:2",
            execution_price="vwap",
            execution_mode="participation",
            participation_rate=0.15,
        ),
        cost_policy=CostPolicy(
            commission_rate=0.0002,
            slippage_bps=10.0,
            stamp_tax_rate=0.001,
        ),
    )
    assert req.execution_policy.participation_rate == 0.15
    assert req.cost_policy.slippage_bps == 10.0


def test_fingerprint_changes_with_dataset_hash():
    a = _sample_request()
    b = _sample_request(dataset_hash="other_hash")
    assert compute_request_fingerprint(a) != compute_request_fingerprint(b)


def test_required_fields():
    exec_p, price_p, _, rules = cn_equity_close_signal_next_open()
    with pytest.raises(ValidationError):
        BacktestRequest(
            dataset_hash="x",
            strategy_version="s",
            start_date="2024-01-01",
            end_date="2024-06-30",
            initial_capital=1.0,
            engine="qlib",
            execution_policy=exec_p,
            market_price_policy=price_p,
            trading_rule=rules,
        )


def test_qlib_relaxed_preset_differs():
    _, _, _, cn_rules = cn_equity_close_signal_next_open()
    _, _, _, qlib_rules = research_qlib_relaxed()
    assert qlib_rules.t_plus == 0
    assert cn_rules.t_plus == 1


def test_trade_ledger_fields():
    t = TradeRecord(
        trade_id="t1",
        instrument_key="CNStock:000001",
        side="BUY",
        quantity=100.0,
        executed_price=10.5,
        slippage=0.01,
        status="REJECTED",
        reject_reason="limit_up",
    )
    assert t.reject_reason == "limit_up"


def test_backtest_package_no_forbidden_imports():
    root = Path(__file__).resolve().parents[2] / "app/services/research_data/backtest"
    forbidden = ("qlib", "strategy_v2")
    for py in root.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
        joined = " ".join(names).lower()
        for bad in forbidden:
            assert bad not in joined, f"{py.name} imports {bad}"
