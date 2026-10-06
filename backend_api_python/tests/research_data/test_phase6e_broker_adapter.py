"""Phase 6E：Broker Adapter 验收。"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

from app.services.broker_adapter.dedup import ExecutionDeduper
from app.services.broker_adapter.errors import AdapterErrorCode, BrokerAdapterError
from app.services.broker_adapter.mapping import map_broker_status
from app.services.broker_adapter.protocol import BrokerCapabilities

sys.path.insert(0, str(Path(__file__).resolve().parent))
from broker_adapter_golden.golden import (  # noqa: E402
    INST_A,
    make_env,
    prices,
    sample_intent,
)


def test_capabilities_reject_unsupported(tmp_path):
    _, _, portfolio, _, oms, _, adapter = make_env(tmp_path)
    adapter.capabilities = BrokerCapabilities(supports_limit_order=False)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    r = oms.submit_intents(
        [sample_intent(algo="LIMIT", limit_price=50.0, reason="cap")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices=prices(),
    )
    # LIMIT 不可成交或 capability reject — Paper 路径 LIMIT@50 vs px100 → ACK resting
    # 强制 capability：直接测 adapter
    from app.services.oms.protocol import Order

    order = Order(
        order_id="x",
        client_order_id="c",
        instrument_key=INST_A,
        order_type="LIMIT",
        quantity=1,
        limit_price=50,
        idempotency_key="k",
    )
    report = adapter.submit_order(order)
    assert report.status == "REJECT"
    assert AdapterErrorCode.UNSUPPORTED_ORDER_TYPE.value in report.message


def test_paper_submit_fill(tmp_path):
    _, _, portfolio, _, oms, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    r = oms.submit_intents(
        [sample_intent(qty=5, reason="fill")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices=prices(),
    )
    assert r.orders[0].status == "FILLED"
    assert r.fills


def test_cancel_replace(tmp_path):
    _, _, portfolio, _, oms, *_ = make_env(tmp_path)
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    r = oms.submit_intents(
        [sample_intent(qty=5, algo="LIMIT", limit_price=1.0, reason="cxl")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices={INST_A: 100.0},
    )
    assert r.orders[0].status == "ACKNOWLEDGED"
    cancelled = oms.cancel(r.orders[0].order_id)
    assert cancelled.status == "CANCELLED"

    r2 = oms.submit_intents(
        [sample_intent(qty=5, algo="LIMIT", limit_price=1.0, reason="rpl")],
        account_id=acct.account_id,
        portfolio_id=pid,
        prices={INST_A: 100.0},
    )
    replaced = oms.replace(r2.orders[0].order_id, quantity=3.0)
    assert replaced.version == 2


def test_partial_and_reject(tmp_path):
    _, _, portfolio, _, oms, *_ = make_env(tmp_path, mode="SANDBOX")
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    # async SANDBOX → drain
    r = oms.submit_intents(
        [sample_intent(qty=10, reason="partial")],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="SANDBOX",
        prices=prices(),
        metadata={"simulated": {"partial_fills": [4.0, 6.0]}},
    )
    assert r.orders[0].status == "SUBMITTED"
    n = oms.drain_outbox()
    assert n >= 1
    order = oms.get_order(r.orders[0].order_id)
    assert order.status == "FILLED"
    assert len(oms.list_fills(order.order_id)) == 2

    r2 = oms.submit_intents(
        [sample_intent(qty=1, reason="rej")],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="SANDBOX",
        prices=prices(),
        metadata={"simulated": {"reject": True}},
    )
    oms.drain_outbox()
    assert oms.get_order(r2.orders[0].order_id).status in (
        "BROKER_REJECTED",
        "REJECTED",
    )


def test_unknown_recover(tmp_path):
    _, _, portfolio, _, oms, broker_svc, adapter = make_env(
        tmp_path, mode="SANDBOX"
    )
    acct = portfolio.open_account(initial_cash=1_000_000)
    pid = acct.metadata["default_portfolio_id"]
    r = oms.submit_intents(
        [sample_intent(qty=2, reason="unk")],
        account_id=acct.account_id,
        portfolio_id=pid,
        environment="SANDBOX",
        prices=prices(),
        metadata={"simulated": {"timeout_unknown": True}},
    )
    oms.drain_outbox()
    order = oms.get_order(r.orders[0].order_id)
    assert order.status == "UNKNOWN"
    recovered = oms.recover_unknown_order(order.order_id)
    # hidden_success 在簿上为 NEW → ACK
    assert recovered.status in ("ACKNOWLEDGED", "FILLED", "PARTIALLY_FILLED")


def test_dedup_and_ws_reconnect(tmp_path):
    _, _, _, _, _, broker_svc, adapter = make_env(tmp_path, mode="SANDBOX")
    from app.services.oms.protocol import Order

    order = Order(
        order_id="oid1",
        client_order_id="clid1",
        instrument_key=INST_A,
        quantity=3,
        idempotency_key="idem1",
        metadata={"simulated": {"duplicate_execution": True}},
    )
    adapter.submit_order(order)
    seen: list = []
    n = adapter.pump_events(lambda er: seen.append(er))
    # 重复 execution 只算一次
    assert n == 1
    adapter.ws.disconnect()
    adapter.reconnect_ws()
    seen2: list = []
    n2 = adapter.pump_events(lambda er: seen2.append(er))
    # replay 被 dedup 吃掉
    assert n2 == 0


def test_raw_event_index(tmp_path):
    _, registry, _, _, _, broker_svc, _ = make_env(tmp_path, mode="SANDBOX")
    from app.services.oms.protocol import Order

    order = Order(
        order_id="oid2",
        client_order_id="clid2",
        instrument_key=INST_A,
        quantity=1,
        idempotency_key="idem2",
    )
    broker_svc.connect()
    report = broker_svc.submit_order(order)
    assert report.status in ("FILL", "ACK", "UNKNOWN", "REJECT")
    # link 已写
    link = registry.get_order_link_by_client_id("clid2")
    assert link.order_id == "oid2"


def test_map_broker_status():
    assert map_broker_status("NEW") == "ACK"
    assert map_broker_status("partially_filled", broker="alpaca") == "PARTIAL"
    assert map_broker_status("filled", broker="alpaca") == "FILL"


def test_live_forbidden(tmp_path):
    from app.services.broker_adapter import BrokerAdapterService
    from app.services.research_data.canonical_store import LocalCanonicalStore
    from app.services.research_data.registry import LocalJsonRegistry

    store = LocalCanonicalStore(root=tmp_path / "c")
    registry = LocalJsonRegistry(root=tmp_path / "r")
    with pytest.raises(BrokerAdapterError) as ei:
        BrokerAdapterService(store, registry, execution_mode="LIVE")  # type: ignore[arg-type]
    assert ei.value.code == AdapterErrorCode.LIVE_FORBIDDEN


def test_risk_to_oms_sandbox(tmp_path):
    from app.services.portfolio_service.protocol import (
        Account,
        CashBalance,
        PositionDelta,
    )
    from app.services.risk_engine import RiskPolicy
    from app.services.risk_engine.policy import finalize_policy

    _, _, portfolio, risk, oms, *_ = make_env(tmp_path, mode="SANDBOX")
    real = portfolio.open_account(initial_cash=1_000_000)
    pid = real.metadata["default_portfolio_id"]
    acct = Account(
        account_id="r",
        status="ACTIVE",
        cash=CashBalance(available_cash=1_000_000),
        equity=1_000_000,
    )
    px = prices()
    tw = 0.01
    tq = (tw * 1_000_000) / px[INST_A]
    pol = finalize_policy(
        RiskPolicy(
            policy_code="ba",
            policy_version="1",
            max_single_position_weight=0.5,
            max_turnover=1.0,
            max_position_delta_weight=0.5,
        )
    )
    ev = risk.evaluate(
        deltas=[
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
        ],
        account=acct,
        policy=pol,
        prices=px,
        metadata={
            "account_id": real.account_id,
            "portfolio_id": pid,
            "trading_date": "2020-01-02",
            "apply_id": "ap",
        },
    )
    assert ev.order_intents
    r = oms.submit_intents(
        ev.order_intents,
        account_id=real.account_id,
        portfolio_id=pid,
        risk_run_id=ev.risk_run_id,
        policy_hash=ev.policy_hash,
        environment="SANDBOX",
        prices=px,
    )
    oms.drain_outbox()
    assert oms.get_order(r.orders[0].order_id).status in (
        "FILLED",
        "PARTIALLY_FILLED",
        "ACKNOWLEDGED",
        "BROKER_REJECTED",
    )


def test_alpaca_credentials_reject_live(monkeypatch):
    from app.services.broker_adapter.credentials import load_alpaca_paper_credentials

    monkeypatch.setenv("ALPACA_PAPER_BASE_URL", "https://api.alpaca.markets")
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "k")
    monkeypatch.setenv("ALPACA_PAPER_API_SECRET", "s")
    with pytest.raises(BrokerAdapterError):
        load_alpaca_paper_credentials()


def test_alpaca_adapter_importable():
    from app.services.broker_adapter.adapters.alpaca import AlpacaPaperAdapter

    assert AlpacaPaperAdapter.execution_mode == "ALPACA_PAPER"


def test_ast_isolation():
    pkg = (
        Path(__file__).resolve().parents[2] / "app" / "services" / "broker_adapter"
    )
    forbidden = ("qlib", "strategy_v2", "live_trading", "pending_order", "DataSourceFactory")
    for py in pkg.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    for frag in forbidden:
                        assert frag not in name, f"{py}: {name}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for frag in forbidden:
                    assert frag not in mod, f"{py}: {mod}"
