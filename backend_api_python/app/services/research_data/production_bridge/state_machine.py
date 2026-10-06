"""Production Bundle 状态机：合法迁移表。"""

from __future__ import annotations

from .protocol import BundleStatus

# from → allowed next
_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"VALIDATED", "RETIRED"}),
    "VALIDATED": frozenset({"CANDIDATE", "RETIRED"}),
    "CANDIDATE": frozenset({"APPROVED", "RETIRED"}),
    "APPROVED": frozenset({"DEPLOYED", "RETIRED"}),
    "DEPLOYED": frozenset({"PAUSED", "RETIRED"}),
    "PAUSED": frozenset({"DEPLOYED", "RETIRED"}),
    "RETIRED": frozenset(),
}

# APPROVED 及之后禁止 mutate artifact（状态可迁，内容不可改）
IMMUTABLE_STATUSES: frozenset[str] = frozenset(
    {"APPROVED", "DEPLOYED", "PAUSED", "RETIRED"}
)

CV_PASS_STATUSES: frozenset[str] = frozenset(
    {"PASSED", "PASSED_WITH_EXPECTED_DIFF"}
)


class StateTransitionError(ValueError):
    """非法状态迁移。"""


def can_transition(current: str, target: str) -> bool:
    """是否允许 current → target。"""
    return target in _TRANSITIONS.get(str(current), frozenset())


def assert_transition(current: str, target: BundleStatus | str) -> None:
    """非法则硬失败。"""
    if not can_transition(current, str(target)):
        raise StateTransitionError(
            f"illegal transition {current!r} → {target!r}"
        )


def is_immutable(status: str) -> bool:
    """APPROVED 后 Bundle 内容不可变。"""
    return str(status) in IMMUTABLE_STATUSES


def cv_allows_candidate(cv_status: str) -> bool:
    """CV 门禁：仅 PASSED* 可晋升 CANDIDATE。"""
    return str(cv_status) in CV_PASS_STATUSES
