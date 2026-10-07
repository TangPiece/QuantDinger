"""钉住 9B FactorBuildIndex + 9A DatasetHandle → Run 索引字段。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.research_data.contracts import DatasetHandle
from app.services.research_data.feature_factor_platform.protocol import FactorBuildIndex

from .hashing import compute_run_content_hash
from .identity import evaluation_run_index_key, new_evaluation_id
from .protocol import (
    ENGINE_VERSION,
    EVALUATION_RUN_INDEX_SCHEMA,
    EvaluationRun,
    EvaluationRunIndex,
    QualityGateVerdict,
    RunStatus,
)


def pin_evaluation_run(
    *,
    factor_ref: str,
    dataset_ref: str,
    build_index: FactorBuildIndex,
    handle: DatasetHandle,
    policy_id: str,
    policy_content_hash: str,
    policy_version: str,
    start_date: str,
    end_date: str,
    status: RunStatus,
    gate_verdict: QualityGateVerdict = "PASS",
    gate_reasons: list[str] | None = None,
    evaluation_hash: str = "",
    metric_hash: str = "",
    group_evaluation_hash: str = "",
    stability_hash: str = "",
    resolved_direction: str = "",
    quality_score_uri: str = "",
    evaluation_id: str | None = None,
    published_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[EvaluationRunIndex, EvaluationRun]:
    ts = published_at or datetime.now(timezone.utc)
    run_hash = compute_run_content_hash(
        factor_hash=build_index.factor_hash,
        dataset_hash=handle.dataset_hash,
        factor_dataset_id=build_index.factor_dataset_id,
        policy_content_hash=policy_content_hash,
        start_date=start_date,
        end_date=end_date,
        layout=build_index.layout,
    )
    eid = evaluation_id or new_evaluation_id()
    idx = EvaluationRunIndex(
        schema_version=EVALUATION_RUN_INDEX_SCHEMA,
        engine_version=ENGINE_VERSION,
        evaluation_id=eid,
        run_content_hash=run_hash,
        status=status,
        factor_ref=factor_ref,
        factor_hash=build_index.factor_hash,
        dataset_ref=dataset_ref,
        dataset_hash=handle.dataset_hash,
        factor_dataset_id=build_index.factor_dataset_id,
        policy_id=policy_id,
        policy_content_hash=policy_content_hash,
        evaluation_policy_version=policy_version,
        start_date=start_date,
        end_date=end_date,
        evaluation_hash=evaluation_hash,
        metric_hash=metric_hash,
        group_evaluation_hash=group_evaluation_hash,
        stability_hash=stability_hash,
        resolved_direction=resolved_direction,
        gate_verdict=gate_verdict,
        gate_reasons=list(gate_reasons or []),
        quality_score_uri=quality_score_uri,
        immutable=True,
        published_at=ts,
        metadata={
            "r2_key": evaluation_run_index_key(run_content_hash=run_hash),
            **(metadata or {}),
        },
    )
    run = EvaluationRun(
        evaluation_id=eid,
        run_content_hash=run_hash,
        status=status,
        factor_ref=factor_ref,
        factor_hash=build_index.factor_hash,
        dataset_ref=dataset_ref,
        dataset_hash=handle.dataset_hash,
        factor_dataset_id=build_index.factor_dataset_id,
        policy_id=policy_id,
        policy_content_hash=policy_content_hash,
        evaluation_policy_version=policy_version,
        start_date=start_date,
        end_date=end_date,
        evaluation_hash=evaluation_hash,
        metric_hash=metric_hash,
        group_evaluation_hash=group_evaluation_hash,
        stability_hash=stability_hash,
        resolved_direction=resolved_direction,
        gate_verdict=gate_verdict,
        gate_reasons=list(gate_reasons or []),
        quality_score_uri=quality_score_uri,
        published_at=ts,
        metadata=dict(idx.metadata),
    )
    return idx, run


__all__ = ["pin_evaluation_run"]
