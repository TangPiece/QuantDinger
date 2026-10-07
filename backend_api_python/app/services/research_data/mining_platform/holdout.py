"""Holdout 评价：仅报告，不参与 ranking。"""

from __future__ import annotations

from typing import Any, Mapping

from .protocol import FactorCandidate, MiningPlatformInject


def attach_holdout_metrics(
    candidate: FactorCandidate,
    *,
    holdout_eval_id: str = "",
    metrics: Mapping[str, Any] | None = None,
    inject: MiningPlatformInject | None = None,
) -> FactorCandidate:
    meta = dict(metrics or {})
    if inject and inject.holdout_metrics_by_expression_hash:
        inj_m = inject.holdout_metrics_by_expression_hash.get(candidate.expression_hash)
        if inj_m:
            meta = dict(inj_m)
    if not holdout_eval_id and inject and inject.skip_build_eval:
        holdout_eval_id = f"holdout_inject_{candidate.expression_hash[:12]}"
    return candidate.model_copy(
        update={
            "holdout_evaluation_id": holdout_eval_id,
            "holdout_metrics": meta,
        }
    )


__all__ = ["attach_holdout_metrics"]
