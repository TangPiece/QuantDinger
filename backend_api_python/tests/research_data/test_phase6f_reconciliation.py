"""Phase 6F：Reconciliation / Execution Reconciliation 验收。"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

from app.services.broker_adapter.protocol import BrokerOrderView
from app.services.oms import OMSError
from app.services.reconciliation_service import FindingsError
from app.services.reconciliation_service.protocol import BrokerExecutionView

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reconciliation_golden.golden import (  # noqa: E402
    INST_A,
    make_env,
    prices,
    sample_intent,
)


def _domain_isolation() -> bool:
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "reconciliation_service"
    )
    forbidden = (
        "qlib",
        "strategy_v2",
        "live_trading",
        "pending_order",
        "DataSourceFactory",
    )
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    for frag in forbidden:
                        if frag in name:
                            return False
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for frag in forbidden:
                    if frag in mod:
                        return False
    return True


def test_ast_isolation():
    assert _domain_isolation()


def test_match_after_fill(tmp_path):
    _, _, portfolio, oms, recon, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    r = oms.submit_intents(
        [sample_intent(qty=5, reason="match")],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="SANDBOX",
        prices=prices(),
    )
    oms.drain_outbox()
    assert oms.get_order(r.orders[0].order_id).status == "FILLED"
    run = recon.run(acct.account_id, pid, mode="EOD", salt="match")
    assert run.critical_count == 0
    types = {f.type for f in recon.list_findings(run_id=run.run_id)}
    assert "POSITION_MISMATCH" not in types
    assert "UNEXPECTED_FILL" not in types
    assert not recon.is_trading_blocked(acct.account_id)


def test_fill_mismatch_80_vs_100(tmp_path):
    _, _, portfolio, oms, recon, adapter, _ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    r = oms.submit_intents(
        [sample_intent(qty=100, reason="fill80")],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="SANDBOX",
        prices=prices(),
    )
    oms.drain_outbox()
    fills = oms.list_fills(r.orders[0].order_id)
    assert fills
    eid = str((fills[0].metadata or {}).get("broker_execution_id") or "")
    run = recon.run(
        acct.account_id,
        pid,
        mode="EOD",
        salt="fill80",
        inject={
            "drop_execution_ids": [eid],
            "inject_executions": [
                {
                    "broker_execution_id": eid,
                    "client_order_id": r.orders[0].client_order_id,
                    "quantity": 80.0,
                    "price": 100.0,
                }
            ],
        },
    )
    findings = recon.list_findings(run_id=run.run_id)
    assert any(f.type == "FILL_MISMATCH" for f in findings)


def test_position_mismatch(tmp_path):
    _, _, portfolio, oms, recon, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    oms.submit_intents(
        [sample_intent(qty=10, reason="pos")],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="SANDBOX",
        prices=prices(),
    )
    oms.drain_outbox()
    run = recon.run(
        acct.account_id,
        pid,
        mode="EOD",
        salt="pos",
        inject={"force_broker_position": {INST_A: 3.0}},
    )
    findings = recon.list_findings(run_id=run.run_id)
    assert any(f.type == "POSITION_MISMATCH" for f in findings)
    # |Δ|=7 ≥ 1 → CRITICAL
    assert run.critical_count >= 1
    assert recon.is_trading_blocked(acct.account_id)


def test_unexpected_order_and_fill(tmp_path):
    _, _, portfolio, oms, recon, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    run = recon.run(
        acct.account_id,
        pid,
        mode="EOD",
        salt="unexp",
        inject={
            "inject_open_orders": [
                BrokerOrderView(
                    client_order_id="ghost_clid",
                    instrument_key=INST_A,
                    side="BUY",
                    quantity=1.0,
                    status="NEW",
                )
            ],
            "inject_executions": [
                BrokerExecutionView(
                    broker_execution_id="ghost_exec",
                    client_order_id="ghost_clid",
                    quantity=1.0,
                    price=100.0,
                )
            ],
        },
    )
    types = {f.type for f in recon.list_findings(run_id=run.run_id)}
    assert "UNEXPECTED_ORDER" in types
    assert "UNEXPECTED_FILL" in types
    assert run.critical_count >= 2
    assert recon.is_trading_blocked(acct.account_id)


def test_missing_fill_via_drop(tmp_path):
    _, _, portfolio, oms, recon, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    r = oms.submit_intents(
        [sample_intent(qty=2, reason="miss")],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="SANDBOX",
        prices=prices(),
    )
    oms.drain_outbox()
    fills = oms.list_fills(r.orders[0].order_id)
    eid = str((fills[0].metadata or {}).get("broker_execution_id") or "")
    run = recon.run(
        acct.account_id,
        pid,
        mode="EOD",
        salt="miss",
        inject={"drop_execution_ids": [eid]},
    )
    assert any(
        f.type == "MISSING_FILL" for f in recon.list_findings(run_id=run.run_id)
    )


def test_duplicate_execution_not_double_counted(tmp_path):
    """重复 broker_execution_id 在 Snapshot 中去重不产生 UNEXPECTED。"""
    _, _, portfolio, oms, recon, adapter, _ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    r = oms.submit_intents(
        [sample_intent(qty=1, reason="dup")],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="SANDBOX",
        prices=prices(),
        metadata={"simulated": {"duplicate_execution": True}},
    )
    oms.drain_outbox()
    # pump 可能吞掉重复；Snapshot recent_executions 通常只一条
    run = recon.run(acct.account_id, pid, mode="EOD", salt="dup")
    fills = oms.list_fills(r.orders[0].order_id)
    # 同一 eid 不应出现两个 UNEXPECTED_FILL
    unexpected = [
        f
        for f in recon.list_findings(run_id=run.run_id)
        if f.type == "UNEXPECTED_FILL"
    ]
    assert len(unexpected) == 0
    assert len(fills) >= 1


def test_critical_blocks_new_buy_cancel_ok(tmp_path):
    _, _, portfolio, oms, recon, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    # 先下一笔 resting LIMIT 以便 cancel
    r = oms.submit_intents(
        [sample_intent(qty=5, algo="LIMIT", limit_price=1.0, reason="rest")],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="SANDBOX",
        prices=prices(),
    )
    oms.drain_outbox()
    order = oms.get_order(r.orders[0].order_id)
    assert order.status in ("ACKNOWLEDGED", "SUBMITTED")

    recon.run(
        acct.account_id,
        pid,
        mode="EOD",
        salt="gate",
        inject={
            "inject_open_orders": [
                BrokerOrderView(
                    client_order_id="bad_order",
                    quantity=9,
                    status="NEW",
                    instrument_key=INST_A,
                )
            ]
        },
    )
    assert recon.is_trading_blocked(acct.account_id)

    with pytest.raises(OMSError):
        oms.submit_intents(
            [sample_intent(qty=1, reason="blocked")],
            account_id=acct.account_id,
            portfolio_id=pid,
            environment="SANDBOX",
            prices=prices(),
        )

    # cancel 仍可用
    cancelled = oms.cancel(order.order_id)
    assert cancelled.status == "CANCELLED"


def test_critical_cannot_waive(tmp_path):
    _, _, portfolio, oms, recon, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    run = recon.run(
        acct.account_id,
        pid,
        mode="EOD",
        salt="waive",
        inject={
            "inject_executions": [
                {
                    "broker_execution_id": "x1",
                    "quantity": 1,
                    "price": 1,
                }
            ]
        },
    )
    crit = [
        f
        for f in recon.list_findings(run_id=run.run_id)
        if f.severity == "CRITICAL"
    ]
    assert crit
    with pytest.raises(FindingsError):
        recon.waive(crit[0].finding_id)


def test_resolve_clears_gate(tmp_path):
    _, _, portfolio, oms, recon, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    run = recon.run(
        acct.account_id,
        pid,
        mode="EOD",
        salt="resolve",
        inject={
            "inject_open_orders": [
                BrokerOrderView(
                    client_order_id="tmp_bad",
                    quantity=1,
                    status="NEW",
                    instrument_key=INST_A,
                )
            ]
        },
    )
    assert recon.is_trading_blocked(acct.account_id)
    for f in recon.list_findings(run_id=run.run_id):
        if f.severity == "CRITICAL":
            recon.acknowledge(f.finding_id)
            recon.resolve(f.finding_id)
    assert not recon.is_trading_blocked(acct.account_id)
