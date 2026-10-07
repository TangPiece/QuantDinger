"""Phase 8F：Alert 生命周期 FSM（不触达 Strategy lifecycle）。"""

from __future__ import annotations

from .protocol import AlertStatus

_FORWARD: dict[AlertStatus, set[AlertStatus]] = {
    "OPEN": {"ACKNOWLEDGED", "INVESTIGATING", "RESOLVED"},
    "ACKNOWLEDGED": {"INVESTIGATING", "RESOLVED"},
    "INVESTIGATING": {"RESOLVED"},
    "RESOLVED": {"REOPENED"},
    "REOPENED": {"ACKNOWLEDGED", "INVESTIGATING", "RESOLVED"},
}


class InvalidAlertTransitionError(RuntimeError):
    """非法告警状态迁移。"""


def assert_alert_transition(current: AlertStatus, nxt: AlertStatus) -> None:
    allowed = _FORWARD.get(current, set())
    if nxt not in allowed:
        raise InvalidAlertTransitionError(f"invalid alert transition {current}→{nxt}")


__all__ = ["InvalidAlertTransitionError", "assert_alert_transition"]
