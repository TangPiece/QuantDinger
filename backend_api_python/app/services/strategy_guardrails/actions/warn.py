"""Phase 8G：WARN 动作（仅审计，不改 Runtime）。"""

from __future__ import annotations

from ..protocol import GovernanceEvent, StrategyRuntimeState


def apply_warn(
    runtime: StrategyRuntimeState,
    *,
    event: GovernanceEvent,
) -> StrategyRuntimeState:
    _ = event
    if runtime.runtime_status == "ACTIVE":
        return runtime.model_copy(update={"runtime_status": "DEGRADED"})
    return runtime


__all__ = ["apply_warn"]
