"""Factor Library lifecycle FSM。"""

from __future__ import annotations

from .protocol import LibraryLifecycle


class LibraryLifecycleError(ValueError):
    pass


_ALLOWED: dict[LibraryLifecycle, set[LibraryLifecycle]] = {
    "DRAFT": {"CANDIDATE", "RETIRED"},
    "CANDIDATE": {"EVALUATING", "RETIRED"},
    "EVALUATING": {"VALIDATED", "RETIRED"},
    "VALIDATED": {"APPROVED", "RETIRED"},
    "APPROVED": {"ACTIVE", "DEPRECATED", "RETIRED"},
    "ACTIVE": {"DEPRECATED", "RETIRED"},
    "DEPRECATED": {"RETIRED", "ACTIVE"},
    "RETIRED": set(),
}


def assert_transition(current: LibraryLifecycle, target: LibraryLifecycle) -> None:
    allowed = _ALLOWED.get(current, set())
    if target not in allowed and current != target:
        raise LibraryLifecycleError(
            f"illegal lifecycle transition {current!r} -> {target!r}"
        )


def can_activate(current: LibraryLifecycle) -> bool:
    return current in ("APPROVED", "DEPRECATED")


def can_deprecate(current: LibraryLifecycle) -> bool:
    return current in ("APPROVED", "ACTIVE")


def can_retire(current: LibraryLifecycle) -> bool:
    return current != "RETIRED"


__all__ = [
    "LibraryLifecycleError",
    "assert_transition",
    "can_activate",
    "can_deprecate",
    "can_retire",
]
