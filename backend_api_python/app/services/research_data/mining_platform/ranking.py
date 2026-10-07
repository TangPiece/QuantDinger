"""MiningScore 排序（禁用 holdout）。"""

from __future__ import annotations

from datetime import datetime, timezone

from .protocol import FactorCandidate, MiningScore


def compute_selection_score(
    candidate: FactorCandidate,
    *,
    quality_total: float,
    ic_score: float,
) -> float:
    """Holdout 不参与 selection。"""
    if candidate.status in ("REDUNDANT", "DEDUP_REMOVED", "SCREENED_OUT"):
        return 0.0
    return 0.6 * float(quality_total) + 0.4 * float(ic_score)


def rank_candidates(
    candidates: list[FactorCandidate],
    *,
    quality_by_eval_id: dict[str, float],
    ic_by_eval_id: dict[str, float],
) -> tuple[list[FactorCandidate], list[MiningScore]]:
    scored: list[tuple[FactorCandidate, MiningScore]] = []
    now = datetime.now(timezone.utc)
    for c in candidates:
        if c.status not in ("EVALUATED", "RANKED", "REDUNDANT"):
            continue
        if not c.evaluation_id:
            continue
        qt = quality_by_eval_id.get(c.evaluation_id, 0.0)
        ic = ic_by_eval_id.get(c.evaluation_id, 0.0)
        sel = compute_selection_score(c, quality_total=qt, ic_score=ic)
        ms = MiningScore(
            candidate_id=c.candidate_id,
            mining_run_id=c.mining_run_id,
            selection_score=sel,
            ic_score=ic,
            quality_total=qt,
            raw={"evaluation_id": c.evaluation_id},
            published_at=now,
        )
        scored.append((c, ms))

    scored.sort(key=lambda x: x[1].selection_score, reverse=True)
    ranked_cands: list[FactorCandidate] = []
    scores: list[MiningScore] = []
    for rank, (c, ms) in enumerate(scored, start=1):
        ms = ms.model_copy(update={"rank": rank})
        c = c.model_copy(update={"status": "RANKED", "mining_score": ms.selection_score})
        ranked_cands.append(c)
        scores.append(ms)
    return ranked_cands, scores


__all__ = ["compute_selection_score", "rank_candidates"]
