"""FSM illegal-transition checks + runtime vs lifecycle separation."""

from __future__ import annotations

import pytest

from app.services.strategy_guardrails.fsm import (
    InvalidGuardrailTransitionError,
    assert_incident_transition,
    assert_runtime_transition,
)
from app.services.strategy_promotion.fsm import (
    InvalidPromotionTransitionError,
    assert_environment_transition,
)
from app.services.trading_governance.lifecycle import (
    LifecycleTransitionError,
    assert_transition as assert_lifecycle_transition,
)


def check_promotion_illegal_transitions() -> None:
    with pytest.raises(InvalidPromotionTransitionError):
        assert_environment_transition("REGISTERED", "LIVE")
    with pytest.raises(InvalidPromotionTransitionError):
        assert_environment_transition("SHADOW", "LIVE")
    with pytest.raises(InvalidPromotionTransitionError):
        assert_environment_transition("SHADOW", "REGISTERED")


def check_lifecycle_illegal_transitions() -> None:
    with pytest.raises(LifecycleTransitionError):
        assert_lifecycle_transition("DRAFT", "LIVE")
    with pytest.raises(LifecycleTransitionError):
        assert_lifecycle_transition("SHADOW", "LIVE", scale_level="L4_PRODUCTION")
    with pytest.raises(LifecycleTransitionError):
        assert_lifecycle_transition("RETIRED", "SHADOW")


def check_guardrail_illegal_transitions() -> None:
    with pytest.raises(InvalidGuardrailTransitionError):
        assert_incident_transition("DETECTED", "APPROVED")
    with pytest.raises(InvalidGuardrailTransitionError):
        assert_incident_transition("RESOLVED", "OPEN")
    with pytest.raises(InvalidGuardrailTransitionError):
        assert_runtime_transition("STOPPED", "THROTTLED")


def assert_runtime_paused_not_lifecycle_retired(
    *,
    runtime_status: str,
    lifecycle_phase: str,
) -> None:
    """Runtime PAUSED must not imply lifecycle RETIRED (orthogonal planes)."""
    rt = str(runtime_status or "").upper()
    lc = str(lifecycle_phase or "").upper()
    if rt == "PAUSED":
        assert lc != "RETIRED", "runtime PAUSED must not map to lifecycle RETIRED"
    if lc == "RETIRED":
        assert rt != "PAUSED", "lifecycle RETIRED must not use runtime PAUSED"


def run_fsm_checks() -> dict[str, bool]:
    check_promotion_illegal_transitions()
    check_lifecycle_illegal_transitions()
    check_guardrail_illegal_transitions()
    assert_runtime_paused_not_lifecycle_retired(runtime_status="PAUSED", lifecycle_phase="LIVE")
    assert_runtime_paused_not_lifecycle_retired(runtime_status="ACTIVE", lifecycle_phase="SHADOW")
    return {
        "promotion_illegal": True,
        "lifecycle_illegal": True,
        "guardrail_illegal": True,
        "runtime_lifecycle_invariant": True,
    }


__all__ = [
    "assert_runtime_paused_not_lifecycle_retired",
    "run_fsm_checks",
]
