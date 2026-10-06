"""EvaluationSpec → EvaluationPlan（校验 snapshot / delay / PIT 前提）。"""

from __future__ import annotations

from app.services.research_data.contracts import FactorDatasetRecord

from .hash import compute_evaluation_hash
from .protocol import EvaluationPlan, EvaluationSpec


class EvaluationPlanError(ValueError):
    """评价计划非法。"""


def build_evaluation_plan(
    spec: EvaluationSpec,
    factor_ds: FactorDatasetRecord,
) -> EvaluationPlan:
    """构建不可变 EvaluationPlan；snapshot 缺失则失败。"""
    if not (spec.snapshot_id or "").strip():
        raise EvaluationPlanError(
            "EvaluationSpec.snapshot_id is required; "
            "refusing to evaluate against current universe"
        )
    if not (spec.universe_code or "").strip():
        raise EvaluationPlanError("EvaluationSpec.universe_code is required")
    if not spec.start_date or not spec.end_date:
        raise EvaluationPlanError("evaluation period start_date/end_date required")
    if spec.start_date > spec.end_date:
        raise EvaluationPlanError("start_date must be <= end_date")

    delay = int(spec.return_spec.execution_delay)
    # exit=factor+horizon 的定义下，必须 horizon >= delay，否则 entry>exit
    if spec.return_spec.definition != "close_to_next_open":
        for h in spec.return_spec.horizons:
            if delay > 0 and h < delay:
                raise EvaluationPlanError(
                    f"horizon {h} < execution_delay {delay}: entry would be after exit"
                )

    fhash = factor_ds.dataset_hash or factor_ds.factor_hash
    ehash = compute_evaluation_hash(spec, factor_dataset_hash=fhash)
    return EvaluationPlan(
        evaluation_hash=ehash,
        factor_dataset_id=factor_ds.factor_dataset_id,
        factor_dataset_hash=fhash,
        factor_ref=factor_ds.factor_ref,
        snapshot_id=spec.snapshot_id,
        universe_code=spec.universe_code,
        universe_version=spec.universe_version or "",
        start_date=spec.start_date,
        end_date=spec.end_date,
        frequency=spec.frequency,
        return_spec=spec.return_spec,
        price_policy=spec.price_policy,
        mode=spec.mode,
        evaluator_version=spec.evaluator_version,
        calendar_version=spec.calendar_version,
        exchange=spec.exchange,
        metadata=dict(spec.metadata or {}),
    )
