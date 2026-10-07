"""Phase 8G：THROTTLE → Runtime THROTTLED + caps 乘数。"""

from __future__ import annotations

from typing import Any

from ..bridges.trading_governance import apply_throttle_caps
from ..capital_guard import assert_no_capital_reallocation
from ..fsm import assert_runtime_transition
from ..protocol import StrategyRuntimeState, ThrottleTier
from ..runtime_state import runtime_for_throttle


def apply_throttle(
    runtime: StrategyRuntimeState,
    *,
    tier: ThrottleTier = "THROTTLED_50",
    governance: Any | None = None,
    strategy_id: str = "",
    reason: str = "",
) -> StrategyRuntimeState:
    assert_no_capital_reallocation(action="THROTTLE")
    status, mult = runtime_for_throttle(tier)
    assert_runtime_transition(runtime.runtime_status, status)
    apply_throttle_caps(
        governance,
        strategy_id=strategy_id or runtime.strategy_code,
        multiplier=mult,
        reason=reason,
    )
    return runtime.model_copy(
        update={
            "runtime_status": status,
            "throttle_tier": tier,
            "throttle_multiplier": mult,
        }
    )


__all__ = ["apply_throttle"]
