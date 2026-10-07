"""Phase 7B：ShadowOrder 状态机。"""

from __future__ import annotations

from .protocol import ShadowOrderStatus


class ShadowStateMachineError(RuntimeError):
    pass


_ALLOWED: dict[str, frozenset[str]] = {
    "SUBMITTED": frozenset({"ACCEPTED", "REJECTED", "CANCELLED"}),
    "ACCEPTED": frozenset(
        {"PARTIALLY_FILLED", "FILLED", "EXPIRED", "REJECTED", "CANCELLED"}
    ),
    "PARTIALLY_FILLED": frozenset({"PARTIALLY_FILLED", "FILLED", "EXPIRED", "CANCELLED"}),
    "FILLED": frozenset(),
    "EXPIRED": frozenset(),
    "REJECTED": frozenset(),
    "CANCELLED": frozenset(),
}


def assert_shadow_transition(current: ShadowOrderStatus | str, target: ShadowOrderStatus | str) -> None:
    cur = str(current).upper()
    tgt = str(target).upper()
    if cur == tgt:
        return
    allowed = _ALLOWED.get(cur, frozenset())
    if tgt not in allowed:
        raise ShadowStateMachineError(f"shadow order transition {cur}→{tgt} not allowed")
