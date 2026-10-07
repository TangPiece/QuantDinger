"""Phase 7E：Portfolio / Strategy halt 编排（调 SafetyService；无 auto flatten）。"""

from __future__ import annotations

from typing import Any, Sequence


class GovernanceKillError(RuntimeError):
    pass


def halt_strategy(safety: Any, *, account_id: str, strategy_id: str, reason: str = "") -> None:
    """Strategy scope halt：仅拦新单，不 cancel/flatten。"""
    if safety is None:
        raise GovernanceKillError("safety service required")
    fn = getattr(safety, "emergency_stop", None) or getattr(safety, "kill_strategy", None)
    if not callable(fn):
        raise GovernanceKillError("safety does not support strategy halt")
    fn(account_id, strategy_id=strategy_id, reason=reason or "governance_kill_strategy")


def halt_portfolio(
    safety: Any,
    *,
    account_id: str,
    strategy_ids: Sequence[str],
    reason: str = "",
) -> None:
    """Portfolio scope → ACCOUNT halt + 记录策略集合（不 flatten）。"""
    if safety is None:
        raise GovernanceKillError("safety service required")
    stop = getattr(safety, "emergency_stop", None)
    if callable(stop):
        stop(account_id, reason=reason or "governance_kill_portfolio")
        return
    for sid in strategy_ids:
        halt_strategy(safety, account_id=account_id, strategy_id=sid, reason=reason)
