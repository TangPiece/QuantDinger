"""TrainingJob 组装。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .identity import new_training_job_id
from .protocol import ENGINE_VERSION, TrainingJob, TrainingJobSpec
from .training_config import hash_training_config, normalize_resource_config, normalize_training_config


def pin_training_job(
    spec: TrainingJobSpec,
    *,
    job_id: str | None = None,
    created_at: datetime | None = None,
) -> TrainingJob:
    ts = created_at or datetime.now(timezone.utc)
    cfg = normalize_training_config(spec.training_config)
    return TrainingJob(
        engine_version=ENGINE_VERSION,
        job_id=job_id or new_training_job_id(),
        model_id=spec.model_id,
        model_code=spec.model_code,
        requested_version=spec.requested_version,
        dataset_ref=spec.dataset_ref,
        dataset_hash=spec.dataset_hash,
        snapshot_id=spec.snapshot_id,
        feature_set_id=spec.feature_set_id,
        feature_set_hash=spec.feature_set_hash,
        factor_portfolio_hash=spec.factor_portfolio_hash,
        label_hash=spec.label_hash,
        processor_version=spec.processor_version,
        training_config=cfg,
        training_config_hash=hash_training_config(cfg),
        hyperparameters=dict(spec.hyperparameters or {}),
        resource_config=normalize_resource_config(spec.resource_config),
        framework=str(spec.framework or "").upper(),
        framework_version=spec.framework_version,
        code_version=spec.code_version,
        environment_hash=spec.environment_hash,
        random_seed=spec.random_seed,
        train_start=spec.train_start,
        train_end=spec.train_end,
        validation_start=spec.validation_start,
        validation_end=spec.validation_end,
        idempotency_key=spec.idempotency_key,
        created_at=ts,
        updated_at=ts,
        metadata=dict(spec.metadata or {}),
    )


def run_spec_from_job(job: TrainingJob, **overrides: Any):
    from .protocol import TrainingRunSpec

    data = {
        "job_id": job.job_id,
        "model_id": job.model_id,
        "model_code": job.model_code,
        "requested_model_version": job.requested_version,
        "dataset_ref": job.dataset_ref,
        "dataset_hash": job.dataset_hash,
        "snapshot_id": job.snapshot_id,
        "feature_set_id": job.feature_set_id,
        "feature_set_hash": job.feature_set_hash,
        "factor_portfolio_hash": job.factor_portfolio_hash,
        "label_hash": job.label_hash,
        "processor_version": job.processor_version,
        "training_config": dict(job.training_config),
        "hyperparameters": dict(job.hyperparameters),
        "resource_config": dict(job.resource_config),
        "framework": job.framework,
        "framework_version": job.framework_version,
        "code_version": job.code_version,
        "environment_hash": job.environment_hash,
        "random_seed": job.random_seed,
        "train_start": job.train_start,
        "train_end": job.train_end,
        "validation_start": job.validation_start,
        "validation_end": job.validation_end,
        "idempotency_key": job.idempotency_key,
    }
    data.update(overrides)
    return TrainingRunSpec.model_validate(data)


__all__ = ["pin_training_job", "run_spec_from_job"]
