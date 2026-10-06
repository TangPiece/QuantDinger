"""Account / Portfolio 状态机。"""

from __future__ import annotations

_TRANSITIONS: dict[str, frozenset[str]] = {
    "ACTIVE": frozenset({"PAUSED", "RECONCILIATION_REQUIRED", "CLOSED"}),
    "PAUSED": frozenset({"ACTIVE", "CLOSED", "RECONCILIATION_REQUIRED"}),
    "RECONCILIATION_REQUIRED": frozenset({"ACTIVE", "PAUSED", "CLOSED"}),
    "CLOSED": frozenset(),
}


class PortfolioStateError(ValueError):
    """非法账户/组合状态迁移。"""


def can_transition(current: str, target: str) -> bool:
    return target in _TRANSITIONS.get(str(current), frozenset())


def assert_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise PortfolioStateError(f"illegal portfolio transition {current!r} → {target!r}")


def is_applyable(status: str) -> bool:
    return str(status) == "ACTIVE"
