"""Pin ModelEvaluationRun。"""

from __future__ import annotations

from datetime import datetime, timezone

from .hashing import compute_run_content_hash
from .identity import new_evaluation_run_id
from .policy import hash_policy, resolve_policy
from .protocol import EVALUATOR_VERSION, ModelEvaluationRequest, ModelEvaluationRun


def pin_evaluation_run(
    request: ModelEvaluationRequest,
    *,
    evaluation_run_id: str | None = None,
    created_at: datetime | None = None,
) -> ModelEvaluationRun:
    ts = created_at or datetime.now(timezone.utc)
    policy = resolve_policy(request.policy_code)
    pch = hash_policy(policy)
    rid = evaluation_run_id or new_evaluation_run_id()
    rhash = compute_run_content_hash(
        model_version_id=request.model_version_id,
        evaluation_dataset_hash=request.evaluation_dataset_hash
        or request.dataset_hash,
        policy_content_hash=pch,
        evaluation_start=request.evaluation_start,
        evaluation_end=request.evaluation_end,
        label_hash=request.label_hash,
        feature_set_hash=request.feature_set_hash,
        snapshot_id=request.snapshot_id,
    )
    return ModelEvaluationRun(
        evaluation_run_id=rid,
        run_content_hash=rhash,
        model_version_id=request.model_version_id,
        dataset_hash=request.dataset_hash,
        evaluation_dataset_hash=request.evaluation_dataset_hash
        or request.dataset_hash,
        snapshot_id=request.snapshot_id,
        feature_set_hash=request.feature_set_hash,
        label_hash=request.label_hash,
        evaluation_policy_version=f"{policy.policy_code}@{policy.version}",
        policy_content_hash=pch,
        evaluator_version=EVALUATOR_VERSION,
        evaluation_start=request.evaluation_start,
        evaluation_end=request.evaluation_end,
        status="QUEUED",
        created_at=ts,
        metadata=dict(request.metadata or {}),
    )


__all__ = ["pin_evaluation_run"]
