"""Phase 8E：PerformanceComparisonRun FSM（不触达 Strategy lifecycle）。"""

from __future__ import annotations

from .protocol import ComparisonRunStatus

_ORDER: tuple[ComparisonRunStatus, ...] = (
    "CREATED",
    "COLLECTING",
    "COMPUTING",
    "ATTRIBUTING",
    "EVALUATED",
    "PUBLISHED",
)


class InvalidComparisonTransitionError(RuntimeError):
    """非法对比 Run 状态迁移。"""


def assert_transition(current: ComparisonRunStatus, nxt: ComparisonRunStatus) -> None:
    if nxt == "FAILED":
        return
    if current == "FAILED":
        raise InvalidComparisonTransitionError("cannot leave FAILED")
    if current == "PUBLISHED":
        raise InvalidComparisonTransitionError("PUBLISHED is terminal")
    try:
        idx = _ORDER.index(current)
        nidx = _ORDER.index(nxt)
    except ValueError as exc:
        raise InvalidComparisonTransitionError(f"unknown status: {current}/{nxt}") from exc
    if nidx != idx + 1:
        raise InvalidComparisonTransitionError(f"invalid {current}→{nxt}")


def pipeline_statuses() -> list[ComparisonRunStatus]:
    """正常管线阶段顺序。"""
    return list(_ORDER)


__all__ = [
    "InvalidComparisonTransitionError",
    "assert_transition",
    "pipeline_statuses",
]
