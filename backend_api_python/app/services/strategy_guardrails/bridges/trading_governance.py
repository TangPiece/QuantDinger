"""Phase 8G：7E throttle / pause 适配（scale-down caps，不 scale-up）。"""

from __future__ import annotations

from typing import Any


class GovernanceBridgeError(RuntimeError):
    pass


def apply_throttle_caps(
    governance: Any | None,
    *,
    strategy_id: str,
    multiplier: float,
    reason: str = "",
) -> None:
    """通过 metadata 记录 throttle；有 apply_runtime_throttle 则调用。"""
    if governance is None:
        return
    fn = getattr(governance, "apply_runtime_throttle", None)
    if callable(fn):
        fn(strategy_id, multiplier=multiplier, reason=reason)
        return
    recorder = getattr(governance, "_runtime_throttle_log", None)
    if isinstance(recorder, list):
        recorder.append(
            {"strategy_id": strategy_id, "multiplier": multiplier, "reason": reason}
        )


def apply_pause_lifecycle(
    governance: Any | None,
    *,
    strategy_id: str,
    reason: str = "",
) -> None:
    if governance is None:
        return
    fn = getattr(governance, "pause_strategy_runtime", None) or getattr(
        governance, "transition_lifecycle", None
    )
    if callable(fn) and fn.__name__ == "pause_strategy_runtime":
        fn(strategy_id, reason=reason)
        return
    log = getattr(governance, "_runtime_pause_log", None)
    if isinstance(log, list):
        log.append({"strategy_id": strategy_id, "reason": reason})


__all__ = ["GovernanceBridgeError", "apply_pause_lifecycle", "apply_throttle_caps"]
