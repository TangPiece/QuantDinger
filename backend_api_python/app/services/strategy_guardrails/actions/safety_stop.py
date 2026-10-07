"""Phase 8G：Safety STOP NEW ORDERS（6G/7E kill，无 flatten）。"""

from __future__ import annotations

from typing import Any

from ..bridges.safety import safety_stop_new_orders
from ..fsm import assert_runtime_transition
from ..protocol import StrategyRuntimeState


def apply_safety_stop(
    runtime: StrategyRuntimeState,
    *,
    safety: Any | None = None,
    account_id: str = "",
    strategy_id: str = "",
    reason: str = "",
) -> StrategyRuntimeState:
    sid = strategy_id or runtime.strategy_code
    acct = account_id or str(runtime.metadata.get("account_id") or "acct_default")
    safety_stop_new_orders(
        safety,
        account_id=acct,
        strategy_id=sid,
        reason=reason or "guardrail_safety_stop",
    )
    cur = runtime.runtime_status
    if cur != "STOPPED":
        if cur != "STOPPING":
            assert_runtime_transition(cur, "STOPPING")
        assert_runtime_transition("STOPPING", "STOPPED")
    return runtime.model_copy(update={"runtime_status": "STOPPED", "recovery_check_passed": False})


__all__ = ["apply_safety_stop"]
