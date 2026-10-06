"""Simulated 侧订单状态（≠ OMS 状态机）。"""

from __future__ import annotations

_TRANSITIONS: dict[str, frozenset[str]] = {
    "NEW": frozenset({"PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED"}),
    "PARTIALLY_FILLED": frozenset({"PARTIALLY_FILLED", "FILLED", "CANCELED"}),
    "FILLED": frozenset(),
    "CANCELED": frozenset(),
    "REJECTED": frozenset(),
}


class SimulatedStateError(ValueError):
    """非法 simulated 状态迁移。"""


def assert_sim_transition(current: str, target: str) -> None:
    allowed = _TRANSITIONS.get(str(current), frozenset())
    if target not in allowed and current != target:
        raise SimulatedStateError(f"illegal sim transition {current!r} → {target!r}")
