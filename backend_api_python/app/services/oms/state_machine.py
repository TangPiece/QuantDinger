"""Order 状态机白名单；非法迁移抛错。"""

from __future__ import annotations

from typing import Iterable

from .protocol import OrderStatus

# 合法边：from → frozenset(to)
_TRANSITIONS: dict[str, frozenset[str]] = {
    "CREATED": frozenset({"VALIDATED", "REJECTED"}),
    "VALIDATED": frozenset({"SUBMITTED", "REJECTED"}),
    "SUBMITTED": frozenset(
        {"ACKNOWLEDGED", "BROKER_REJECTED", "UNKNOWN", "CANCEL_PENDING"}
    ),
    "ACKNOWLEDGED": frozenset(
        {
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCEL_PENDING",
            "REPLACE_PENDING",
            "BROKER_REJECTED",
            "UNKNOWN",
        }
    ),
    "PARTIALLY_FILLED": frozenset(
        {
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCEL_PENDING",
            "REPLACE_PENDING",
            "UNKNOWN",
        }
    ),
    "FILLED": frozenset(),
    "CANCEL_PENDING": frozenset({"CANCELLED", "FILLED", "PARTIALLY_FILLED", "UNKNOWN"}),
    "CANCELLED": frozenset(),
    "REPLACE_PENDING": frozenset(
        {"REPLACED", "ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "UNKNOWN"}
    ),
    "REPLACED": frozenset(
        {"ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING"}
    ),
    "REJECTED": frozenset(),
    "BROKER_REJECTED": frozenset(),
    "UNKNOWN": frozenset({"ACKNOWLEDGED", "FILLED", "CANCELLED", "BROKER_REJECTED"}),
}

TERMINAL: frozenset[str] = frozenset(
    {"FILLED", "CANCELLED", "REJECTED", "BROKER_REJECTED"}
)


class StateMachineError(ValueError):
    """非法状态迁移。"""


def can_transition(current: OrderStatus | str, target: OrderStatus | str) -> bool:
    cur = str(current)
    tgt = str(target)
    if cur == tgt and cur in ("PARTIALLY_FILLED",):
        return True
    return tgt in _TRANSITIONS.get(cur, frozenset())


def assert_transition(current: OrderStatus | str, target: OrderStatus | str) -> None:
    if not can_transition(current, target):
        raise StateMachineError(f"illegal transition {current!r} → {target!r}")


def allowed_targets(current: OrderStatus | str) -> frozenset[str]:
    return _TRANSITIONS.get(str(current), frozenset())


def is_terminal(status: OrderStatus | str) -> bool:
    return str(status) in TERMINAL


def is_open(status: OrderStatus | str) -> bool:
    return str(status) not in TERMINAL and str(status) not in ("REPLACED",)


def all_statuses() -> Iterable[str]:
    return tuple(_TRANSITIONS.keys())
