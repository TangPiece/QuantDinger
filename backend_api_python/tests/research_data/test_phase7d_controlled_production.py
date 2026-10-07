"""Phase 7D：Controlled Live Production 验收。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from app.services.broker_adapter.adapters.alpaca.controlled_live_adapter import (
    FakeControlledLiveAdapter,
)
from app.services.controlled_live.gate import ControlledLiveDenied
from app.services.controlled_live.session import SessionImmutableError, assert_session_immutable
from app.services.production_runtime.runner import ProductionRuntimeError, ProductionRuntimeService
from app.services.research_data.contracts import OrderIntent
from app.services.shadow_trading.gateway import EnvironmentViolation, OrderExecutionGateway

sys.path.insert(0, str(Path(__file__).resolve().parent))
from controlled_production_golden.golden import (  # noqa: E402
    ACCOUNT_ID,
    DATASET_HASH,
    FEATURE_VERSION,
    MODEL_VERSION,
    SNAPSHOT_ID,
    STRATEGY_ID,
    FakeControlledMarketData,
    FakeReconciliationService,
    _limit_intent,
    make_production_env,
)


def test_session_lock_rejects_model_change(tmp_path):
    _, _, controlled, _, _, _, _, _ = make_production_env(tmp_path / "lock")
    sess = controlled._session
    assert sess is not None
    with pytest.raises(SessionImmutableError):
        assert_session_immutable(sess, {"model_version": "other"})


def test_multi_tick_multi_order_within_budget(tmp_path):
    _, _, controlled, runtime, broker, _, _, _ = make_production_env(
        tmp_path / "multi", max_orders=3
    )
    r1 = runtime.tick()
    r2 = runtime.tick()
    assert r1.orders_submitted == 1 and r2.orders_submitted == 1
    assert broker.submit_count == 2
    assert controlled._session.status == "OPEN"


def test_max_orders_denied(tmp_path):
    _, _, controlled, _, broker, _, _, _ = make_production_env(
        tmp_path / "max", max_orders=1
    )
    controlled.submit_single_intent(_limit_intent(trace="a"), strategy_id=STRATEGY_ID)
    with pytest.raises(ControlledLiveDenied):
        controlled.submit_single_intent(_limit_intent(trace="b", price=99.0), strategy_id=STRATEGY_ID)
    assert broker.submit_count == 1


def test_filled_does_not_kill_session_when_budget_remaining(tmp_path):
    _, _, controlled, _, broker, _, _, _ = make_production_env(
        tmp_path / "filled", max_orders=3
    )
    order = controlled.submit_single_intent(
        _limit_intent(trace="fill1"), strategy_id=STRATEGY_ID
    )
    assert order.status in ("FILLED", "ACCEPTED")
    assert broker.submit_count == 1
    assert controlled._session.status == "OPEN"
    assert not controlled._session.stop_reason.startswith("filled")


def test_md_stale_halts(tmp_path):
    _, _, _, runtime, _, md, _, _ = make_production_env(tmp_path / "stale", max_orders=3)
    md.set_stale(stale=True)
    result = runtime.tick()
    assert result.halted
    assert runtime.session.stop_reason == "md_stale"


def test_recon_critical_halts(tmp_path):
    recon = FakeReconciliationService(critical=True)
    _, _, controlled, runtime, _, _, _, _ = make_production_env(
        tmp_path / "recon", max_orders=3, recon=recon
    )
    runtime.tick()
    assert controlled._session.stop_reason == "recon_mismatch"
    with pytest.raises(ControlledLiveDenied):
        controlled.submit_single_intent(
            _limit_intent(trace="after_recon"), strategy_id=STRATEGY_ID
        )


def test_unknown_query_only_no_resubmit(tmp_path):
    broker = FakeControlledLiveAdapter(next_submit_raises_unknown=True)
    _, _, controlled, _, broker, _, _, _ = make_production_env(
        tmp_path / "unk", broker=broker, max_orders=3
    )
    order = controlled.submit_single_intent(
        _limit_intent(trace="unk"), strategy_id=STRATEGY_ID
    )
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
    controlled.recover_unknown(cid)
    assert broker.submit_count == 1


def test_live_forbidden_gateway_and_production_runtime():
    gw = OrderExecutionGateway()
    with pytest.raises(EnvironmentViolation, match="LIVE forbidden"):
        gw.submit_real("LIVE", None, FakeControlledLiveAdapter(), submit_fn=lambda o: o)
    with pytest.raises(ProductionRuntimeError, match="LIVE environment forbidden"):
        ProductionRuntimeService(None, None).start(  # type: ignore[arg-type]
            "bundle_x", environment="LIVE"
        )


def test_operator_status_and_metrics(tmp_path):
    _, _, controlled, runtime, _, _, _, ops = make_production_env(tmp_path / "ops", max_orders=3)
    runtime.tick()
    snap = runtime.status()
    assert snap.strategy_lock.get("dataset_hash") == DATASET_HASH
    assert snap.strategy_lock.get("feature_version") == FEATURE_VERSION
    assert snap.strategy_lock.get("snapshot_id") == SNAPSHOT_ID
    metrics = ops.metrics.snapshot()
    assert any(k.startswith("controlled_live_tick_total") for k in metrics)


def test_crash_recovery_unknown(tmp_path):
    broker = FakeControlledLiveAdapter(next_submit_raises_unknown=True)
    _, _, controlled, runtime, broker, _, _, _ = make_production_env(
        tmp_path / "recover", broker=broker, max_orders=3
    )
    controlled.submit_single_intent(_limit_intent(trace="rec"), strategy_id=STRATEGY_ID)
    cid = next(iter(controlled._orders))
    broker._orders[cid] = {
        "id": "brk_rec2",
        "client_order_id": cid,
        "symbol": "AAPL",
        "status": "filled",
        "filled_qty": "1",
        "filled_avg_price": "100",
    }
    runtime.recover()
    assert broker.submit_count == 1


def test_daily_loss_halt_via_metadata(tmp_path):
    _, _, controlled, runtime, _, _, _, _ = make_production_env(
        tmp_path / "pnl", max_orders=3
    )
    runtime.tick(metadata={"daily_pnl": -99999.0})
    assert controlled._session.stop_reason == "daily_loss_limit"
