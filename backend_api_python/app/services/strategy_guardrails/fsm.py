"""Phase 8G：Incident / Runtime 状态机转移。"""

from __future__ import annotations

from .protocol import IncidentStatus, RuntimeStatus

_INCIDENT_TRANSITIONS: dict[str, set[str]] = {
    "DETECTED": {"OPEN", "REVIEW_REQUIRED", "RESOLVED"},
    "OPEN": {"TRIAGED", "MITIGATING", "REVIEW_REQUIRED", "RESOLVED"},
    "TRIAGED": {"MITIGATING", "REVIEW_REQUIRED", "RESOLVED"},
    "MITIGATING": {"RESOLVED", "REVIEW_REQUIRED"},
    "REVIEW_REQUIRED": {"APPROVED", "REJECTED", "RESOLVED"},
    "APPROVED": {"RESOLVED"},
    "REJECTED": {"OPEN", "RESOLVED"},
    "RESOLVED": set(),
}

_RUNTIME_TRANSITIONS: dict[str, set[str]] = {
    "ACTIVE": {"DEGRADED", "THROTTLED", "PAUSED", "STOPPING", "STOPPED", "ROLLBACK_PENDING"},
    "DEGRADED": {"ACTIVE", "THROTTLED", "PAUSED", "STOPPED"},
    "THROTTLED": {"ACTIVE", "DEGRADED", "PAUSED", "STOPPED"},
    "PAUSED": {"ACTIVE", "STOPPED", "ROLLBACK_PENDING"},
    "STOPPING": {"STOPPED"},
    "STOPPED": {"ACTIVE", "ROLLBACK_PENDING"},
    "ROLLBACK_PENDING": {"ROLLING_BACK", "PAUSED", "STOPPED"},
    "ROLLING_BACK": {"PAUSED", "STOPPED", "ACTIVE"},
}


class InvalidGuardrailTransitionError(ValueError):
    pass


def assert_incident_transition(current: IncidentStatus | str, target: IncidentStatus | str) -> None:
    cur = str(current or "").strip().upper()
    tgt = str(target or "").strip().upper()
    allowed = _INCIDENT_TRANSITIONS.get(cur, set())
    if tgt not in allowed:
        raise InvalidGuardrailTransitionError(f"incident {cur} -> {tgt} not allowed")


def assert_runtime_transition(current: RuntimeStatus | str, target: RuntimeStatus | str) -> None:
    cur = str(current or "").strip().upper()
    tgt = str(target or "").strip().upper()
    if cur == tgt:
        return
    allowed = _RUNTIME_TRANSITIONS.get(cur, set())
    if tgt not in allowed:
        raise InvalidGuardrailTransitionError(f"runtime {cur} -> {tgt} not allowed")


__all__ = [
    "InvalidGuardrailTransitionError",
    "assert_incident_transition",
    "assert_runtime_transition",
]
