"""ModelVersion lifecycle FSM（ACTIVE ≠ Strategy LIVE）。"""

from __future__ import annotations

from .protocol import ModelVersionLifecycle


class ModelLifecycleError(ValueError):
    pass


_ALLOWED: dict[ModelVersionLifecycle, set[ModelVersionLifecycle]] = {
    "DRAFT": {"TRAINING", "RETIRED"},
    "TRAINING": {"TRAINED", "RETIRED"},
    "TRAINED": {"EVALUATING", "DEPRECATED", "RETIRED"},
    "EVALUATING": {"VALIDATED", "RETIRED"},
    "VALIDATED": {"APPROVED", "RETIRED"},
    "APPROVED": {"ACTIVE", "DEPRECATED", "RETIRED"},
    "ACTIVE": {"DEPRECATED", "RETIRED"},
    "DEPRECATED": {"RETIRED", "ACTIVE"},
    "RETIRED": set(),
}


def assert_transition(
    current: ModelVersionLifecycle, target: ModelVersionLifecycle
) -> None:
    allowed = _ALLOWED.get(current, set())
    if target not in allowed and current != target:
        raise ModelLifecycleError(
            f"illegal lifecycle transition {current!r} -> {target!r}"
        )


def can_activate(current: ModelVersionLifecycle) -> bool:
    return current in ("APPROVED", "DEPRECATED")


def can_deprecate(current: ModelVersionLifecycle) -> bool:
    return current in ("APPROVED", "ACTIVE", "TRAINED", "VALIDATED")


def can_retire(current: ModelVersionLifecycle) -> bool:
    return current != "RETIRED"


__all__ = [
    "ModelLifecycleError",
    "assert_transition",
    "can_activate",
    "can_deprecate",
    "can_retire",
]
