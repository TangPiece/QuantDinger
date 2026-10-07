"""Phase 8G：PAUSE → Runtime PAUSED（Lifecycle 不变）。"""

from __future__ import annotations

from typing import Any

from ..bridges.trading_governance import apply_pause_lifecycle
from ..capital_guard import assert_no_capital_reallocation
from ..fsm import assert_runtime_transition
from ..protocol import StrategyRuntimeState


def apply_pause(
    runtime: StrategyRuntimeState,
    *,
    governance: Any | None = None,
    strategy_id: str = "",
    reason: str = "",
) -> StrategyRuntimeState:
    assert_no_capital_reallocation(action="PAUSE")
    assert_runtime_transition(runtime.runtime_status, "PAUSED")
    apply_pause_lifecycle(
        governance,
        strategy_id=strategy_id or runtime.strategy_code,
        reason=reason,
    )
    return runtime.model_copy(
        update={
            "runtime_status": "PAUSED",
            "throttle_tier": "PAUSED",
            "throttle_multiplier": 0.0,
            "recovery_check_passed": False,
        }
    )


__all__ = ["apply_pause"]
