"""Promotion Gate：9C SUCCESS + PASS → APPROVED entry。"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.research_data.evaluation_platform.protocol import EvaluationRun, FactorQualityScore
from app.services.research_data.mining_platform.protocol import FactorCandidate

from .protocol import FactorLibraryInject, PromotionGateConfig, PromotionGateResult


class PromotionGateError(ValueError):
    pass


def evaluate_promotion_gate(
    *,
    evaluation_run: EvaluationRun,
    quality_score: FactorQualityScore | None,
    candidate: FactorCandidate | None = None,
    mining_run_metadata: Mapping[str, Any] | None = None,
    inject: FactorLibraryInject | None = None,
) -> PromotionGateResult:
    cfg: PromotionGateConfig = (
        inject.gate_config if inject else PromotionGateConfig()
    )
    reasons: list[str] = []
    if not (evaluation_run.evaluation_id or "").strip():
        reasons.append("evaluation_id_missing")
    if evaluation_run.status != "SUCCESS":
        reasons.append(f"evaluation_status_{evaluation_run.status}")
    if evaluation_run.gate_verdict != "PASS":
        reasons.append("evaluation_gate_blocked")

    q_total = 0.0
    if quality_score is not None:
        q_total = float(quality_score.total_score)
        if cfg.min_quality_total > 0 and q_total < cfg.min_quality_total:
            reasons.append("min_quality_total_not_met")

    mt_warning = ""
    if mining_run_metadata:
        mt_warning = str(mining_run_metadata.get("selection_bias_warning") or "")
        if not mt_warning and mining_run_metadata.get("multiple_testing_warning"):
            mt_warning = str(mining_run_metadata.get("multiple_testing_warning"))
    if candidate and candidate.metadata.get("multiple_testing_warning"):
        mt_warning = str(candidate.metadata.get("multiple_testing_warning"))

    complexity_note = ""
    redundancy_note = ""
    if candidate and cfg.record_complexity:
        complexity_note = f"depth={candidate.depth}"
    if candidate and cfg.record_redundancy and candidate.redundant_with:
        redundancy_note = f"redundant_with={candidate.redundant_with}"

    if cfg.require_holdout_fields and candidate:
        if not candidate.holdout_evaluation_id and not candidate.holdout_metrics:
            reasons.append("holdout_fields_required")

    verdict = "PASS" if not reasons else "REJECT"
    return PromotionGateResult(
        verdict=verdict,
        reasons=reasons,
        evaluation_id=evaluation_run.evaluation_id,
        factor_ref=evaluation_run.factor_ref,
        quality_total=q_total,
        multiple_testing_warning=mt_warning,
        complexity_note=complexity_note,
        redundancy_note=redundancy_note,
    )


def assert_promotion_pass(result: PromotionGateResult) -> None:
    if result.verdict != "PASS":
        raise PromotionGateError("; ".join(result.reasons) or "promotion_rejected")


__all__ = [
    "PromotionGateError",
    "assert_promotion_pass",
    "evaluate_promotion_gate",
]
