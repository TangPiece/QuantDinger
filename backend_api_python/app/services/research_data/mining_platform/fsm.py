"""MiningRun 有限状态机。"""

from __future__ import annotations

from .protocol import MiningRunStatus

_TRANSITIONS: dict[MiningRunStatus, set[MiningRunStatus]] = {
    "CREATED": {"RUNNING"},
    "RUNNING": {"SCREENING", "FAILED"},
    "SCREENING": {"EVALUATING", "FAILED"},
    "EVALUATING": {"RANKING", "FAILED"},
    "RANKING": {"COMPLETED", "FAILED"},
    "COMPLETED": set(),
    "FAILED": set(),
}


class MiningFSMError(ValueError):
    pass


def advance(current: MiningRunStatus, nxt: MiningRunStatus) -> MiningRunStatus:
    allowed = _TRANSITIONS.get(current, set())
    if nxt not in allowed:
        raise MiningFSMError(f"invalid transition {current} -> {nxt}")
    return nxt


def pipeline_states() -> list[MiningRunStatus]:
    return ["CREATED", "RUNNING", "SCREENING", "EVALUATING", "RANKING", "COMPLETED"]


__all__ = ["MiningFSMError", "advance", "pipeline_states"]
