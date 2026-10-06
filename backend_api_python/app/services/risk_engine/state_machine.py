"""RiskDecision 聚合规则。"""

from __future__ import annotations

from typing import Sequence

from .protocol import RiskResult, RiskVerdict

_RANK: dict[str, int] = {
    "ALLOW": 0,
    "ALLOW_REDUCE": 1,
    "MODIFY": 2,
    "REJECT": 3,
    "ERROR": 4,
}


def merge_verdicts(results: Sequence[RiskResult]) -> RiskVerdict:
    """任一 REJECT/ERROR 胜出；否则取最高严重度决策。"""
    if not results:
        return "ALLOW"
    best = "ALLOW"
    for r in results:
        v = str(r.decision)
        if _RANK.get(v, 0) > _RANK.get(best, 0):
            best = v  # type: ignore[assignment]
    return best  # type: ignore[return-value]


def is_blocking(verdict: RiskVerdict | str) -> bool:
    return str(verdict) in {"REJECT", "ERROR"}
