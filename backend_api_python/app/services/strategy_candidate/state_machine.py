"""Phase 8B：Candidate 状态机硬规则（无 Shadow / LIVE / 8C Gate）。"""

from __future__ import annotations

from typing import Literal

from .protocol import CandidateStatus

# 合法迁移；终态 REJECTED / EXPIRED 不可再转
_ALLOWED: dict[CandidateStatus, frozenset[CandidateStatus]] = {
    "DRAFT": frozenset({"GENERATED"}),
    "GENERATED": frozenset({"EVALUATING"}),
    "EVALUATING": frozenset({"READY_FOR_VALIDATION", "REJECTED"}),
    "READY_FOR_VALIDATION": frozenset({"VALIDATED", "REJECTED", "EXPIRED"}),
    "VALIDATED": frozenset({"EXPIRED"}),
    "REJECTED": frozenset(),
    "EXPIRED": frozenset(),
}

_FORBIDDEN_TARGET = frozenset(
    {"SHADOW", "LIVE", "PROMOTED_TO_SHADOW", "GATE_PASSED", "DEPLOYED"}
)


class InvalidTransitionError(ValueError):
    """非法状态迁移。"""


def assert_transition(
    from_status: CandidateStatus,
    to_status: CandidateStatus,
) -> None:
    """校验迁移；禁止跳过 GENERATED 直达 VALIDATED 等捷径。"""
    target = str(to_status).strip().upper()
    if target in _FORBIDDEN_TARGET:
        raise InvalidTransitionError(f"forbidden target state: {target}")
    src = str(from_status).strip().upper()  # type: ignore[assignment]
    allowed = _ALLOWED.get(src)  # type: ignore[arg-type]
    if allowed is None or target not in allowed:
        raise InvalidTransitionError(f"cannot transition {src} -> {target}")


def is_terminal(status: CandidateStatus) -> bool:
    return status in ("REJECTED", "EXPIRED")


TransitionKind = Literal[
    "generate",
    "start_evaluating",
    "mark_ready",
    "mark_validated",
    "reject",
    "expire",
]


def target_for_action(action: TransitionKind) -> CandidateStatus:
    """门面动作 → 目标状态。"""
    mapping: dict[TransitionKind, CandidateStatus] = {
        "generate": "GENERATED",
        "start_evaluating": "EVALUATING",
        "mark_ready": "READY_FOR_VALIDATION",
        "mark_validated": "VALIDATED",
        "reject": "REJECTED",
        "expire": "EXPIRED",
    }
    return mapping[action]


__all__ = [
    "InvalidTransitionError",
    "assert_transition",
    "is_terminal",
    "target_for_action",
]
