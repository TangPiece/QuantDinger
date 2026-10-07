"""Phase 7E：Gradual Scale / Trading Governance 验收。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from app.services.live_readonly.modes import EnvironmentTransitionError, assert_transition
from app.services.oms import cycle as oms_cycle
from app.services.oms.state_machine import StateMachineError
from app.services.research_data.contracts import OrderIntent
from app.services.shadow_trading.gateway import EnvironmentViolation, OrderExecutionGateway
from app.services.trading_governance.capital import CapitalReject
from app.services.trading_governance.protocol import OrderRiskContext
from app.services.trading_governance.runner import GovernanceError
from app.services.trading_governance.strategy_registry import VersionImmutableError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gradual_scale_golden.golden import (  # noqa: E402
    ACCOUNT_A,
    ACCOUNT_B,
    STRATEGY_A,
    STRATEGY_B,
    VERSION_V1,
    VERSION_V2,
    make_governance_env,
    seed_l1_controlled,
    two_strategy_targets,
)


def test_lifecycle_forbids_draft_to_live(tmp_path):
    gov, _ = make_governance_env(tmp_path / "lc")
    with pytest.raises(GovernanceError):
        gov.transition_lifecycle(STRATEGY_A, "LIVE")


def test_live_version_immutable(tmp_path):
    gov, _ = make_governance_env(tmp_path / "immut")
    pin = gov.register_strategy_version(
        strategy_id=STRATEGY_A,
        strategy_version="live_v",
        is_live=True,
    )
    with pytest.raises(VersionImmutableError):
        from app.services.trading_governance.strategy_registry import assert_version_immutable

        assert_version_immutable(pin, {"model_version": "changed"})


def test_rollback_to_previous_version(tmp_path):
    gov, _ = make_governance_env(tmp_path / "rb")
    lc, pin = gov.rollback_strategy(STRATEGY_A, to_version=VERSION_V1)
    assert lc.active_version == VERSION_V1
    assert not pin.is_live


def test_capital_and_risk_reject(tmp_path):
    gov, _ = make_governance_env(tmp_path / "cap")
    seed_l1_controlled(gov)
    ctx = OrderRiskContext(
        account_id=ACCOUNT_A,
        strategy_id=STRATEGY_A,
        notional=9000.0,
        quantity=1.0,
    )
    with pytest.raises(CapitalReject):
        gov.check_order_allowed(ctx)


def test_scale_up_requires_approval(tmp_path):
    gov, _ = make_governance_env(tmp_path / "scale")
    seed_l1_controlled(gov)
    appr = gov.request_scale_up(STRATEGY_A, account_id=ACCOUNT_A, metrics={"pnl": 9999})
    assert appr.status == "PENDING"
    caps_before = gov.effective_caps(ACCOUNT_A, STRATEGY_A)
    with pytest.raises(GovernanceError):
        gov.apply_scale(STRATEGY_A, approval_id=appr.approval_id)
    gov.approve_scale(appr.approval_id, operator="op1", approval_token="tok")
    gov.apply_scale(STRATEGY_A, approval_id=appr.approval_id)
    caps_after = gov.effective_caps(ACCOUNT_A, STRATEGY_A)
    assert caps_after.max_notional_per_order >= caps_before.max_notional_per_order


def test_aggregation_two_strategies(tmp_path):
    gov, _ = make_governance_env(tmp_path / "agg")
    t1, t2 = two_strategy_targets()
    targets = gov.aggregate_targets([t1, t2], account_id=ACCOUNT_A)
    assert len(targets) == 1
    assert targets[0].net_side == "BUY"
    assert targets[0].net_quantity == pytest.approx(300.0)


def test_attribution_sums(tmp_path):
    gov, _ = make_governance_env(tmp_path / "attr")
    legs = [
        {"strategy_id": STRATEGY_A, "instrument_key": "USStock:AAPL", "side": "BUY", "quantity": 100},
        {"strategy_id": STRATEGY_B, "instrument_key": "USStock:AAPL", "side": "BUY", "quantity": 200},
    ]
    rows = gov.attribute_positions(ACCOUNT_A, legs)
    total = sum(r.quantity for r in rows)
    assert total == pytest.approx(300.0)


def test_account_bind_rejects_wrong_account(tmp_path):
    gov, _ = make_governance_env(tmp_path / "bind")
    seed_l1_controlled(gov)
    ctx = OrderRiskContext(
        account_id=ACCOUNT_B,
        strategy_id=STRATEGY_A,
        notional=100.0,
        quantity=1.0,
    )
    with pytest.raises(Exception):
        gov.check_order_allowed(ctx)


def test_live_forbidden_without_governance(tmp_path):
    gw = OrderExecutionGateway()
    from app.services.broker_adapter.adapters.alpaca.controlled_live_adapter import (
        FakeControlledLiveAdapter,
    )

    with pytest.raises(EnvironmentViolation):
        gw.submit_real(
            "LIVE",
            None,
            FakeControlledLiveAdapter(),
            submit_fn=lambda o: o,
        )
    with pytest.raises(EnvironmentTransitionError):
        assert_transition(
            "LIVE_CONTROLLED",
            "LIVE",
            production_ready=True,
            governance_live_authorized=False,
        )


def test_live_allowed_with_authorization(tmp_path):
    gov, _ = make_governance_env(tmp_path / "live")
    seed_l1_controlled(gov)
    from app.services.trading_governance.protocol import ScaleState

    gov._scale[STRATEGY_A] = ScaleState(
        strategy_id=STRATEGY_A,
        account_id=ACCOUNT_A,
        current_level="L4_PRODUCTION",
    )
    os.environ["LIVE_ENV_APPROVAL"] = "true"
    gov.authorize_live_environment(
        ACCOUNT_A, strategy_id=STRATEGY_A, operator="op", approval_token="x"
    )
    assert gov.is_live_authorized(ACCOUNT_A, STRATEGY_A)
    assert_transition(
        "LIVE_CONTROLLED",
        "LIVE",
        production_ready=True,
        governance_live_authorized=True,
    )


def test_oms_live_requires_metadata(tmp_path):
    assert "LIVE" in oms_cycle._ALLOWED_ENV
    intent = OrderIntent(
        instrument_key="USStock:AAPL",
        side="BUY",
        quantity=1.0,
        execution_algorithm="LIMIT",
        limit_price=1.0,
    )

    class _W:
        def get_by_idempotency_for_intent(self, *a, **k):
            return None

        def persist_order(self, *a, **k):
            pass

    with pytest.raises(StateMachineError):
        oms_cycle.run_submit_intents(
            [intent],
            account_id=ACCOUNT_A,
            portfolio_id="p1",
            environment="LIVE",
            writer=_W(),
            broker_port=object(),
        )
