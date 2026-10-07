"""Phase 7C：Controlled Live 验收。"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

from app.services.broker_adapter.adapters.alpaca.controlled_live_adapter import (
    FakeControlledLiveAdapter,
)
from app.services.broker_adapter.errors import BrokerAdapterError
from app.services.controlled_live.gate import ControlledLiveDenied, ControlledLiveGate
from app.services.controlled_live.runner import ControlledLiveService
from app.services.live_readonly.modes import EnvironmentTransitionError, assert_transition
from app.services.oms import cycle as oms_cycle
from app.services.research_data.contracts import KillSwitchRecord, OrderIntent
from app.services.shadow_trading.gateway import EnvironmentViolation, OrderExecutionGateway

sys.path.insert(0, str(Path(__file__).resolve().parent))
from controlled_live_golden.golden import (  # noqa: E402
    ACCOUNT_ID,
    DATASET_HASH,
    MODEL_VERSION,
    STRATEGY_ID,
    STRATEGY_VERSION,
    make_env,
)


def _controlled_roots() -> list[Path]:
    base = Path(__file__).resolve().parents[2] / "app" / "services"
    return [
        base / "controlled_live",
        base / "broker_adapter" / "adapters" / "alpaca",
    ]


def test_ast_no_delete_patch_orders():
    """live_trading_transport 禁止 DELETE/PATCH orders。"""
    transport = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "broker_adapter"
        / "adapters"
        / "alpaca"
        / "live_trading_transport.py"
    )
    tree = ast.parse(transport.read_text(encoding="utf-8"), filename=str(transport))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "request" and node.args:
                if isinstance(node.args[0], ast.Constant):
                    m = str(node.args[0].value).upper()
                    if m in ("DELETE", "PATCH"):
                        pytest.fail(f"forbidden {m} in live_trading_transport")


def test_cancel_replace_hard_raise():
    ad = FakeControlledLiveAdapter()
    with pytest.raises(BrokerAdapterError):
        ad.cancel_order("x")
    with pytest.raises(BrokerAdapterError):
        ad.replace_order("x")


def test_oms_allowed_env_controlled_not_live():
    assert "LIVE_CONTROLLED" in oms_cycle._ALLOWED_ENV
    assert oms_cycle.live_env_requires_governance()


def test_gateway_live_forbidden():
    gw = OrderExecutionGateway()
    with pytest.raises(EnvironmentViolation, match="LIVE forbidden"):
        gw.submit_real("LIVE", None, FakeControlledLiveAdapter(), submit_fn=lambda o: o)


def test_env_ladder_live_readonly_to_controlled():
    os.environ["PRODUCTION_READY"] = "true"
    assert_transition("LIVE_READONLY", "LIVE_CONTROLLED", production_ready=True)
    with pytest.raises(EnvironmentTransitionError):
        assert_transition("PAPER", "LIVE_CONTROLLED", production_ready=True)


def test_submit_denied_outside_controlled(tmp_path):
    _, _, _, controlled, _ = make_env(tmp_path / "deny_env")
    controlled._environment = "SHADOW"
    with pytest.raises(ControlledLiveDenied):
        controlled.submit_single_intent(
            OrderIntent(
                instrument_key="USStock:AAPL",
                side="BUY",
                quantity=1.0,
                execution_algorithm="LIMIT",
                limit_price=100.0,
                trace_id="t1",
            ),
            strategy_id=STRATEGY_ID,
        )


def test_market_rejected(tmp_path):
    _, _, _, controlled, _ = make_env(tmp_path / "mkt")
    with pytest.raises(ControlledLiveDenied):
        controlled.submit_single_intent(
            OrderIntent(
                instrument_key="USStock:AAPL",
                side="BUY",
                quantity=1.0,
                execution_algorithm="MARKET",
                trace_id="t_mkt",
            ),
            strategy_id=STRATEGY_ID,
        )


def test_gate_qty_symbol_approval_kill(tmp_path):
    _, registry, _, controlled, _ = make_env(tmp_path / "gate")
    gate = ControlledLiveGate(registry)

    bad_intent = OrderIntent(
        instrument_key="USStock:MSFT",
        side="BUY",
        quantity=1.0,
        execution_algorithm="LIMIT",
        limit_price=100.0,
    )
    assert not gate.evaluate(
        environment="LIVE_CONTROLLED",
        session=controlled._session,
        intent=bad_intent,
        approval=controlled._approval,
    ).allowed

    registry.set_kill_switch(
        KillSwitchRecord(scope="ACCOUNT", scope_id=ACCOUNT_ID, engaged=True, reason="test")
    )
    good = OrderIntent(
        instrument_key="USStock:AAPL",
        side="BUY",
        quantity=1.0,
        execution_algorithm="LIMIT",
        limit_price=100.0,
    )
    assert not gate.evaluate(
        environment="LIVE_CONTROLLED",
        session=controlled._session,
        intent=good,
        approval=controlled._approval,
    ).allowed


def test_session_second_order_denied(tmp_path):
    _, _, _, controlled, broker = make_env(tmp_path / "max1")
    intent = OrderIntent(
        instrument_key="USStock:AAPL",
        side="BUY",
        quantity=1.0,
        execution_algorithm="LIMIT",
        limit_price=100.0,
        trace_id="first",
    )
    controlled.submit_single_intent(intent, strategy_id=STRATEGY_ID)
    assert broker.submit_count == 1
    with pytest.raises(ControlledLiveDenied):
        controlled.submit_single_intent(
            OrderIntent(
                instrument_key="USStock:AAPL",
                side="BUY",
                quantity=1.0,
                execution_algorithm="LIMIT",
                limit_price=99.0,
                trace_id="second",
            ),
            strategy_id=STRATEGY_ID,
        )


def test_timeout_recover_query_only(tmp_path):
    broker = FakeControlledLiveAdapter(next_submit_raises_unknown=True)
    _, _, _, controlled, broker = make_env(tmp_path / "unk", broker=broker)
    intent = OrderIntent(
        instrument_key="USStock:AAPL",
        side="BUY",
        quantity=1.0,
        execution_algorithm="LIMIT",
        limit_price=100.0,
        trace_id="unk",
    )
    order = controlled.submit_single_intent(intent, strategy_id=STRATEGY_ID)
    assert order.status == "UNKNOWN"
    assert broker.submit_count == 1
    cid = order.client_order_id
    broker._orders[cid] = {
        "id": "brk_rec",
        "client_order_id": cid,
        "symbol": "AAPL",
        "status": "filled",
        "filled_qty": "1",
        "filled_avg_price": "100",
    }
    recovered = controlled.recover_unknown(cid)
    assert recovered.status in ("FILLED", "RECOVERED")
    assert broker.submit_count == 1


def test_lineage_and_compare(tmp_path):
    _, _, shadow, controlled, _ = make_env(tmp_path / "cmp")
    intent = OrderIntent(
        instrument_key="USStock:AAPL",
        side="BUY",
        quantity=2.0,
        execution_algorithm="LIMIT",
        limit_price=100.0,
        trace_id="cmp1",
    )
    order = controlled.submit_single_intent(intent, strategy_id=STRATEGY_ID)
    assert order.lineage.get("dataset_hash") == DATASET_HASH
    assert order.lineage.get("model_version") == MODEL_VERSION
    shadow.submit_intent(
        OrderIntent(
            instrument_key="USStock:AAPL",
            side="BUY",
            quantity=2.0,
            execution_algorithm="MARKET",
            trace_id="sh1",
        )
    )
    report = controlled.compare_shadow_vs_real(order.order_id)
    assert report.run_id and report.findings


def test_live_controlled_gateway_allows_fake_submit():
    gw = OrderExecutionGateway()
    broker = FakeControlledLiveAdapter()
    from app.services.oms.protocol import Order

    o = Order(
        order_id="o1",
        client_order_id="c1",
        quantity=1.0,
        order_type="LIMIT",
        limit_price=1.0,
        instrument_key="USStock:AAPL",
    )
    gw.submit_real("LIVE_CONTROLLED", o, broker, submit_fn=broker.submit_order)
    assert broker.submit_count == 1
