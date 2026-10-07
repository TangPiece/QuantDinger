"""Phase 7B：Live MD + Shadow Trading 验收。"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

from app.services.live_market_data.quality import (
    FLAG_DEDUP,
    FLAG_STALE,
    MarketEventQualityTracker,
)
from app.services.live_market_data.transport import FakeLiveMdTransport
from app.services.live_readonly.modes import EnvironmentTransitionError, assert_transition
from app.services.oms import cycle as oms_cycle
from app.services.oms.protocol import Order
from app.services.research_data.contracts import OrderIntent
from app.services.shadow_trading.gateway import (
    EnvironmentViolation,
    OrderExecutionGateway,
    is_real_broker,
)
from app.services.shadow_trading.oms import ShadowOmsError
from app.services.shadow_trading.session import SessionImmutableError, merge_session_update
from app.services.shadow_trading.simulator import QuoteLike, ShadowExecutionSimulator, SimulatorConfig

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shadow_trading_golden.golden import (  # noqa: E402
    ACCOUNT_ID,
    DATASET_HASH,
    MODEL_VERSION,
    STRATEGY_VERSION,
    make_env,
)


class _FakeRealBroker:
    broker_id = "alpaca_live"
    execution_mode = "LIVE"
    base_url = "https://api.alpaca.markets"

    def submit_order(self, order: Order):
        return order


def _pkg_roots() -> list[Path]:
    base = Path(__file__).resolve().parents[2] / "app" / "services"
    return [base / "shadow_trading", base / "live_market_data"]


def test_ast_no_post_orders():
    for root in _pkg_roots():
        for py in root.rglob("*.py"):
            if py.name != "transport.py":
                continue
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == "request" and node.args:
                        if isinstance(node.args[0], ast.Constant):
                            if str(node.args[0].value).upper() == "POST":
                                pytest.fail(f"{py}: request(POST...) forbidden")


def test_oms_allowed_env_no_live():
    assert "LIVE" not in oms_cycle._ALLOWED_ENV


def test_gateway_deny_shadow_real_broker():
    gw = OrderExecutionGateway()
    order = Order(order_id="x", client_order_id="x", quantity=1.0)
    broker = _FakeRealBroker()
    assert is_real_broker(broker)
    with pytest.raises(EnvironmentViolation, match="REAL_BROKER_ORDER denied"):
        gw.submit_real("SHADOW", order, broker, submit_fn=broker.submit_order)


def test_env_ladder_paper_live_readonly_blocked():
    os.environ["PRODUCTION_READY"] = "true"
    with pytest.raises(EnvironmentTransitionError):
        assert_transition("PAPER", "LIVE_READONLY", production_ready=True)
    assert_transition("PAPER", "SHADOW", production_ready=True)
    assert_transition("SHADOW", "LIVE_READONLY", production_ready=True)


def test_market_limit_sim_and_ledger(tmp_path):
    _, _, _, _, shadow, _ = make_env(tmp_path / "sim")
    intent_m = OrderIntent(
        instrument_key="USStock:AAPL",
        side="BUY",
        quantity=10.0,
        execution_algorithm="MARKET",
        trace_id="t_mkt",
    )
    order = shadow.submit_intent(intent_m)
    execs = shadow.simulate_fills_for_symbol("AAPL", bid=99.9, ask=100.1)
    assert execs
    pnl = shadow.get_shadow_pnl()
    assert pnl["cash"] < 100_000.0

    sim = ShadowExecutionSimulator(SimulatorConfig(max_fill_qty=3.0))
    from app.services.shadow_trading.protocol import ShadowOrder
    from datetime import datetime, timezone

    lo = ShadowOrder(
        order_id="lo1",
        symbol="AAPL",
        side="BUY",
        quantity=10.0,
        order_type="LIMIT",
        limit_price=101.0,
        status="ACCEPTED",
        risk_approved=True,
        created_at=datetime.now(timezone.utc).isoformat(),
        client_order_id="cid_lim",
    )
    u1, e1 = sim.try_fill(lo, QuoteLike(bid=99.5, ask=100.5))
    assert e1 and u1.filled_quantity == 3.0
    u2, e2 = sim.try_fill(u1, QuoteLike(bid=99.5, ask=100.5))
    assert e2 and u2.filled_quantity == 6.0


def test_risk_gate_blocks_order(tmp_path):
    _, _, _, _, shadow, _ = make_env(tmp_path / "risk")

    def deny(_i):
        return False, "SIZE_LIMIT"

    shadow._risk = deny
    with pytest.raises(ShadowOmsError):
        shadow.submit_intent(
            OrderIntent(
                instrument_key="USStock:AAPL",
                side="BUY",
                quantity=1.0,
                trace_id="deny1",
            )
        )


def test_shadow_session_immutable(tmp_path):
    _, _, _, _, shadow, _ = make_env(tmp_path / "sess")
    session = shadow._session
    assert session
    with pytest.raises(SessionImmutableError):
        merge_session_update(session, {"dataset_hash": "other"})


def test_quality_flags_dedup_stale():
    from app.services.live_market_data.adapter import quote_from_alpaca, to_market_event_quote

    tr = MarketEventQualityTracker(stale_after_sec=1.0)
    q = quote_from_alpaca("AAPL", {"ap": 1, "bp": 1, "t": "2010-01-01T00:00:00Z"})
    ev = to_market_event_quote(q)
    ev2 = tr.annotate(ev)
    assert FLAG_STALE in ev2.quality_flags
    ev3 = tr.annotate(ev)
    assert FLAG_DEDUP in ev3.quality_flags


def test_compare_delta(tmp_path):
    _, _, _, _, shadow, _ = make_env(tmp_path / "cmp")
    shadow.simulate_fills_for_symbol("AAPL", bid=99.9, ask=100.1)
    report = shadow.compare_with_live(ACCOUNT_ID)
    aapl = next(f for f in report.findings if f.symbol == "AAPL")
    assert aapl.qty_delta != 0 or aapl.shadow_qty != aapl.live_qty


def test_transport_rejects_post_orders():
    tr = FakeLiveMdTransport()
    from app.services.broker_adapter.errors import AdapterErrorCode, BrokerAdapterError

    with pytest.raises(BrokerAdapterError) as exc:
        tr.request("POST", "/v2/orders")
    assert exc.value.code == AdapterErrorCode.LIVE_READONLY_FORBIDDEN


@pytest.mark.skipif(
    not os.environ.get("ALPACA_LIVE_API_KEY") or not os.environ.get("ALPACA_LIVE_API_SECRET"),
    reason="opt-in real Alpaca Data GET",
)
def test_opt_in_real_data_get():
    os.environ.setdefault("PRODUCTION_READY", "true")
    from app.services.live_market_data.transport import AlpacaLiveMdTransport

    tr = AlpacaLiveMdTransport()
    raw = tr.get_latest_quote("AAPL")
    assert raw
