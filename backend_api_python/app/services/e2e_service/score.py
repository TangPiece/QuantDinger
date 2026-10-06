"""Phase 6I：E2E ConsistencyScore 计算。"""

from __future__ import annotations

from typing import Sequence

from .hash import derive_score_id
from .protocol import ConsistencyScore, ScenarioResult


def compute_consistency_score(
    results: Sequence[ScenarioResult],
    *,
    run_id: str,
    session_id: str = "",
    audit_event_count: int = 0,
    safety_events: int = 0,
) -> ConsistencyScore:
    """根据场景结果聚合完成度（0~1）。"""
    if not results:
        return ConsistencyScore(
            score_id=derive_score_id(run_id=run_id, session_id=session_id),
            run_id=run_id,
            session_id=session_id,
        )
    ok = [r for r in results if r.status == "OK"]
    n = len(results)
    signal_c = 1.0 if all(r.dataset_hash for r in results) else 0.0
    order_c = sum(1 for r in ok if r.intent_fingerprint or r.virtual_orders) / n
    exec_c = sum(
        1
        for r in ok
        if r.order_ids or (r.mode == "SHADOW" and r.virtual_orders)
    ) / n
    pos_c = sum(
        1 for r in ok if not r.reconciliation_critical and r.status == "OK"
    ) / n
    recon_c = sum(1 for r in ok if not r.reconciliation_critical) / n
    audit_c = min(1.0, audit_event_count / max(n * 2, 1))
    safety_c = 1.0 if safety_events >= 0 else 0.0
    if any(r.scenario_id == "E2E-010" for r in results):
        safety_c = max(safety_c, 1.0 if any(r.blocked_by_safety for r in results) else 0.5)
    overall = (
        signal_c
        + order_c
        + exec_c
        + pos_c
        + recon_c
        + audit_c
        + safety_c
    ) / 7.0
    return ConsistencyScore(
        score_id=derive_score_id(run_id=run_id, session_id=session_id),
        run_id=run_id,
        session_id=session_id,
        signal_consistency=signal_c,
        order_consistency=order_c,
        execution_consistency=exec_c,
        position_consistency=pos_c,
        reconciliation_score=recon_c,
        audit_coverage=audit_c,
        safety_coverage=safety_c,
        overall=overall,
        metadata={"scenario_count": n, "ok_count": len(ok)},
    )
