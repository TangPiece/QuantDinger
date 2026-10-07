"""Phase 8G：RESUME 必经 RECOVERY_CHECK。"""

from __future__ import annotations

from ..fsm import assert_runtime_transition
from ..protocol import StrategyRuntimeState


class ResumeBlockedError(RuntimeError):
    pass


def apply_resume(
    runtime: StrategyRuntimeState,
    *,
    recovery_ok: bool,
    auto_resume_allowed: bool = False,
    decision_approved: bool = False,
) -> StrategyRuntimeState:
    if runtime.runtime_status not in ("PAUSED", "STOPPED", "THROTTLED", "DEGRADED"):
        return runtime
    if not recovery_ok and not decision_approved:
        if auto_resume_allowed and recovery_ok is False:
            raise ResumeBlockedError("recovery check failed")
        raise ResumeBlockedError("recovery check failed; resume requires decision or health")
    assert_runtime_transition(runtime.runtime_status, "ACTIVE")
    return runtime.model_copy(
        update={
            "runtime_status": "ACTIVE",
            "throttle_tier": "NORMAL",
            "throttle_multiplier": 1.0,
            "recovery_check_passed": recovery_ok,
        }
    )


__all__ = ["ResumeBlockedError", "apply_resume"]
