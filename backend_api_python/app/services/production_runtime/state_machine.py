"""Runtime 状态机。"""

from __future__ import annotations

_TRANSITIONS: dict[str, frozenset[str]] = {
    "STARTING": frozenset({"READY", "ERROR", "STOPPING"}),
    "READY": frozenset({"RUNNING", "PAUSED", "STOPPING", "ERROR"}),
    "RUNNING": frozenset({"PAUSED", "DEGRADED", "STOPPING", "ERROR"}),
    "PAUSED": frozenset({"RUNNING", "READY", "STOPPING"}),
    "DEGRADED": frozenset({"RUNNING", "PAUSED", "STOPPING", "ERROR"}),
    "STOPPING": frozenset({"STOPPED", "ERROR"}),
    "STOPPED": frozenset(),
    "ERROR": frozenset({"STOPPING", "STOPPED"}),
}


class RuntimeStateError(ValueError):
    """非法 runtime 状态迁移。"""


def can_transition(current: str, target: str) -> bool:
    return target in _TRANSITIONS.get(str(current), frozenset())


def assert_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise RuntimeStateError(f"illegal runtime transition {current!r} → {target!r}")


def is_tickable(status: str) -> bool:
    return str(status) in {"READY", "RUNNING", "DEGRADED"}
