"""Phase 6D：OMS / Order Lifecycle 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.oms.state_machine import StateMachineError, assert_transition
from app.services.portfolio_service.protocol import Position

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oms_golden.golden import (  # noqa: E402
    DAY,
    INST_A,
    default_policy,
    make_env,
    prices,
    sample_intent,
)


def test_intent_to_order_and_fill(tmp_path):
    _, _, portfolio, _, oms = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    result = oms.submit_intents(
        [sample_intent(qty=100)],
        account_id=acct.account_id,
        portfolio_id=pid,
        risk_run_id="rr1",
        policy_hash="ph1",
        prices=prices(),
    )
    assert len(result.orders) == 1
    order = result.orders[0]
    assert order.status == "FILLED"
    assert order.filled_quantity == pytest.approx(100)
    assert order.client_order_id
    assert order.idempotency_key
    assert len(result.fills) >= 1
    # 回写 6B
    pos = {p.instrument_key: p for p in portfolio.get_positions(pid)}
    assert INST_A in pos
    assert pos[INST_A].quantity == pytest.approx(100)


def test_idempotency(tmp_path):
    _, _, portfolio, _, oms = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    intent = sample_intent(qty=50, reason="same")
    r1 = oms.submit_intents(
        [intent],
        account_id=acct.account_id,
        portfolio_id=pid,
        risk_run_id="rr",
        prices=prices(),
    )
    r2 = oms.submit_intents(
        [intent],
        account_id=acct.account_id,
        portfolio_id=pid,
        risk_run_id="rr",
        prices=prices(),
    )
    assert r1.orders[0].order_id == r2.orders[0].order_id
    pos = portfolio.get_positions(pid)
    # 只成交一次
    assert pos[0].quantity == pytest.approx(50)


def test_state_machine_illegal():
    with pytest.raises(StateMachineError):
        assert_transition("CREATED", "FILLED")


def test_partial_fill(tmp_path):
    _, _, portfolio, _, oms = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    intent = sample_intent(qty=100, reason="partial")
    # 注入部分成交
    intent = intent.model_copy(
        update={"reason": "partial"},
    )
    result = oms.submit_intents(
        [intent],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices=prices(),
        metadata={
            "paper_broker": {"partial_fills": [40.0, 60.0]},
        },
    )
    order = result.orders[0]
    assert order.status == "FILLED"
    assert order.filled_quantity == pytest.approx(100)
    assert len(result.fills) == 2


def test_cancel(tmp_path):
    _, _, portfolio, _, oms = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    # resting limit：价格不可成交
    result = oms.submit_intents(
        [sample_intent(qty=100, algo="LIMIT", limit_price=5.0, reason="cxl")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices={INST_A: 10.0},
    )
    order = result.orders[0]
    assert order.status == "ACKNOWLEDGED"
    cancelled = oms.cancel(order.order_id, reason="user")
    assert cancelled.status == "CANCELLED"


def test_replace(tmp_path):
    _, _, portfolio, _, oms = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    result = oms.submit_intents(
        [sample_intent(qty=100, algo="LIMIT", limit_price=5.0, reason="rpl")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices={INST_A: 10.0},
    )
    order = result.orders[0]
    replaced = oms.replace(order.order_id, quantity=80.0, limit_price=5.0)
    assert replaced.version == 2
    assert replaced.quantity == pytest.approx(80)
    assert replaced.status == "ACKNOWLEDGED"


def test_unknown(tmp_path):
    _, _, portfolio, _, oms = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    result = oms.submit_intents(
        [sample_intent(qty=10, reason="unk")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices=prices(),
        metadata={"paper_broker": {"timeout_unknown": True}},
    )
    assert result.orders[0].status == "UNKNOWN"


def test_outbox_recorded(tmp_path):
    _, registry, portfolio, _, oms = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    result = oms.submit_intents(
        [sample_intent(qty=10, reason="ob")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices=prices(),
    )
    assert result.outbox_ids
    # 同步路径已 SENT
    pending = registry.list_outbox(limit=10)
    assert all(r.outbox_id not in result.outbox_ids or r.status != "PENDING" for r in pending)


def test_sell_freeze_bridge(tmp_path):
    _, _, portfolio, _, oms = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    # 先买入建仓
    oms.submit_intents(
        [sample_intent(qty=100, reason="buy")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices=prices(),
    )
    # 再卖出
    result = oms.submit_intents(
        [sample_intent(side="SELL", qty=40, reason="sell")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices=prices(),
    )
    assert result.orders[0].status == "FILLED"
    pos = {p.instrument_key: p for p in portfolio.get_positions(pid)}
    assert pos[INST_A].quantity == pytest.approx(60)
    assert pos[INST_A].frozen_quantity == pytest.approx(0)


def test_risk_to_oms_chain(tmp_path):
    _, _, portfolio, risk, oms = make_env(tmp_path)
    from app.services.portfolio_service.protocol import Account, CashBalance
    from oms_golden.golden import sample_intent as _
    from app.services.portfolio_service.protocol import PositionDelta

    acct = Account(
        account_id="acc_chain",
        status="ACTIVE",
        cash=CashBalance(available_cash=1_000_000),
        equity=1_000_000,
    )
    # 开真实账户以便 OMS 回写
    real = portfolio.open_account(initial_cash=1_000_000)
    pid = real.metadata["default_portfolio_id"]
    px = prices()
    tw = 0.05
    tq = (tw * 1_000_000) / px[INST_A]
    deltas = [
        PositionDelta(
            instrument_key=INST_A,
            current_weight=0.0,
            target_weight=tw,
            delta_weight=tw,
            current_quantity=0.0,
            target_quantity=tq,
            delta_quantity=tq,
            side="BUY",
            notional=tq * px[INST_A],
        )
    ]
    ev = risk.evaluate(
        deltas=deltas,
        account=acct,
        policy=default_policy(),
        prices=px,
        metadata={
            "account_id": real.account_id,
            "portfolio_id": pid,
            "trading_date": DAY.isoformat(),
            "apply_id": "ap_chain",
        },
    )
    assert ev.order_intents
    result = oms.submit_intents(
        ev.order_intents,
        account_id=real.account_id,
        portfolio_id=pid,
        risk_run_id=ev.risk_run_id,
        policy_hash=ev.policy_hash,
        prices=px,
    )
    assert result.orders
    assert result.orders[0].status == "FILLED"


def test_ast_isolation():
    pkg = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "oms"
    )
    forbidden_mods = ("qlib", "live_trading", "pending_order", "strategy_v2")
    for py in pkg.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    assert name != "qlib" and not name.startswith("qlib.")
                    assert (
                        "broker" not in name.lower()
                        or name.endswith("paper_broker")
                        or ".paper_broker" in name
                        or name.endswith("broker_port")
                        or ".broker_port" in name
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for frag in forbidden_mods:
                    assert frag not in mod, f"{py}: forbidden import {mod}"
                assert "DataSourceFactory" not in mod
                # 允许 OMS 本地 broker_port / paper_broker；禁止真实 broker adapter 包
                if "broker" in mod.lower():
                    assert (
                        "paper_broker" in mod
                        or mod.endswith("paper_broker")
                        or mod.endswith("broker_port")
                        or mod == "broker_port"
                        or mod.endswith(".broker_port")
                    ), f"{py}: unexpected broker import {mod}"
