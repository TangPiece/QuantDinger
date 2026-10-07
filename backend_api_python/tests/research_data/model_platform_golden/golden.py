"""Phase 9F Model Platform golden 环境。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.research_data.model_platform.protocol import (
    ModelArtifactSpec,
    ModelSpec,
    ModelVersion,
    ModelVersionSpec,
    TrainingJobSpec,
    TrainingRun,
    TrainingRunSpec,
)
from app.services.research_data.model_platform.runner import (
    ModelPlatformError,
    ModelPlatformService,
)

GOLDEN_MODEL_CODE = "alpha_lgb_ranker"
GOLDEN_VERSION = "1.0.0"
GOLDEN_DATASET_HASH = "d" * 64
GOLDEN_FEATURE_SET_HASH = "f" * 64
GOLDEN_LABEL_HASH = "b" * 64
GOLDEN_FEATURE_SET_ID = "fs_golden@1.0.0"
GOLDEN_SNAPSHOT_ID = "snap_golden"
GOLDEN_CONFIG = {
    "algorithm": "lightgbm",
    "objective": "regression",
    "parameters": {"learning_rate": 0.03, "num_leaves": 64},
    "num_boost_round": 100,
}


def draft_stub_inject(**kwargs: Any) -> dict[str, Any]:
    section: dict[str, Any] = {"allow_draft_stub": True}
    section.update(kwargs)
    return {"model_platform": section}


def formal_inject(**kwargs: Any) -> dict[str, Any]:
    section: dict[str, Any] = {
        "known_hashes": {
            "dataset_hash": GOLDEN_DATASET_HASH,
            "feature_set_hash": GOLDEN_FEATURE_SET_HASH,
            "label_hash": GOLDEN_LABEL_HASH,
            "snapshot_id": GOLDEN_SNAPSHOT_ID,
        },
        "feature_set_id": GOLDEN_FEATURE_SET_ID,
        "label_hash": GOLDEN_LABEL_HASH,
        "processor_version": "processor@1",
        "snapshot_id": GOLDEN_SNAPSHOT_ID,
    }
    section.update(kwargs)
    return {"model_platform": section}


def make_model_platform_env(tmp: Path) -> ModelPlatformService:
    return ModelPlatformService(tmp / "model_platform_art")


def golden_model_spec(**kwargs: Any) -> ModelSpec:
    data = {
        "model_code": GOLDEN_MODEL_CODE,
        "name": "LightGBM Momentum Prediction",
        "description": "golden ranking model",
        "model_type": "RANKING",
        "framework": "LIGHTGBM",
        "owner": "research",
        "tags": ["golden", "phase9f"],
    }
    data.update(kwargs)
    return ModelSpec.model_validate(data)


def golden_version_spec(**kwargs: Any) -> ModelVersionSpec:
    data = {
        "version": GOLDEN_VERSION,
        "dataset_hash": GOLDEN_DATASET_HASH,
        "snapshot_id": GOLDEN_SNAPSHOT_ID,
        "feature_set_id": GOLDEN_FEATURE_SET_ID,
        "feature_set_hash": GOLDEN_FEATURE_SET_HASH,
        "label_hash": GOLDEN_LABEL_HASH,
        "processor_version": "processor@1",
        "config": dict(GOLDEN_CONFIG),
        "hyperparameters": {"num_boost_round": 100},
        "framework": "LIGHTGBM",
        "framework_version": "3.3.0",
        "code_version": "git:deadbeef",
        "environment_hash": "e" * 64,
        "random_seed": 42,
        "tags": ["golden"],
    }
    data.update(kwargs)
    return ModelVersionSpec.model_validate(data)


def golden_job_spec(*, model_id: str = "", **kwargs: Any) -> TrainingJobSpec:
    data = {
        "model_id": model_id,
        "model_code": GOLDEN_MODEL_CODE,
        "requested_version": GOLDEN_VERSION,
        "dataset_hash": GOLDEN_DATASET_HASH,
        "snapshot_id": GOLDEN_SNAPSHOT_ID,
        "feature_set_id": GOLDEN_FEATURE_SET_ID,
        "feature_set_hash": GOLDEN_FEATURE_SET_HASH,
        "factor_portfolio_hash": "p" * 64,
        "label_hash": GOLDEN_LABEL_HASH,
        "processor_version": "processor@1",
        "training_config": dict(GOLDEN_CONFIG),
        "hyperparameters": {"num_boost_round": 100},
        "resource_config": {"executor": "local", "cpu": 2, "memory_mb": 4096},
        "framework": "LIGHTGBM",
        "framework_version": "3.3.0",
        "code_version": "git:deadbeef",
        "environment_hash": "e" * 64,
        "random_seed": 42,
        "train_start": "2020-01-01",
        "train_end": "2020-06-30",
        "validation_start": "2020-07-01",
        "validation_end": "2020-09-30",
    }
    data.update(kwargs)
    return TrainingJobSpec.model_validate(data)


def golden_training_run_spec(
    *,
    model_id: str = "",
    model_version_id: str = "",
    training_run_id: str = "",
    **kwargs: Any,
) -> TrainingRunSpec:
    data = {
        "training_run_id": training_run_id,
        "model_id": model_id,
        "model_code": GOLDEN_MODEL_CODE,
        "model_version_id": model_version_id,
        "requested_model_version": GOLDEN_VERSION,
        "dataset_hash": GOLDEN_DATASET_HASH,
        "snapshot_id": GOLDEN_SNAPSHOT_ID,
        "feature_set_id": GOLDEN_FEATURE_SET_ID,
        "feature_set_hash": GOLDEN_FEATURE_SET_HASH,
        "factor_portfolio_hash": "p" * 64,
        "label_hash": GOLDEN_LABEL_HASH,
        "processor_version": "processor@1",
        "train_start": "2020-01-01",
        "train_end": "2020-06-30",
        "validation_start": "2020-07-01",
        "validation_end": "2020-09-30",
        "random_seed": 42,
        "training_config": dict(GOLDEN_CONFIG),
        "hyperparameters": {"num_boost_round": 100},
        "framework": "LIGHTGBM",
        "framework_version": "3.3.0",
        "code_version": "git:deadbeef",
        "environment_hash": "e" * 64,
        "status": "QUEUED",
    }
    data.update(kwargs)
    return TrainingRunSpec.model_validate(data)


def golden_artifact_spec(model_version_id: str = "pending", **kwargs: Any) -> ModelArtifactSpec:
    data = {
        "model_version_id": model_version_id,
        "artifact_type": "model_bundle",
        "artifact_uri": f"qd/artifacts/model/{model_version_id}/",
        "checksum": "a" * 64,
        "file_size": 1024,
        "framework": "LIGHTGBM",
        "framework_version": "3.3.0",
        "feature_schema_uri": "feature_schema.json",
        "environment_uri": "environment.json",
    }
    data.update(kwargs)
    return ModelArtifactSpec.model_validate(data)


def advance_run_to_succeeded(
    svc: ModelPlatformService, training_run_id: str
) -> TrainingRun:
    """合法逐步推进到 SUCCEEDED（不自动建 ModelVersion）。"""
    svc.update_training_run_status(training_run_id, "PREPARING")
    svc.update_training_run_status(training_run_id, "RUNNING")
    svc.update_training_run_status(training_run_id, "FINALIZING")
    return svc.update_training_run_status(training_run_id, "SUCCEEDED")


def create_succeeded_run(
    svc: ModelPlatformService,
    *,
    model_id: str,
    training_run_id: str = "",
) -> TrainingRun:
    run = svc.create_training_run(
        golden_training_run_spec(model_id=model_id, training_run_id=training_run_id)
    )
    return advance_run_to_succeeded(svc, run.training_run_id)


def create_formal_version(
    svc: ModelPlatformService,
    *,
    model_id: str,
    version: str = GOLDEN_VERSION,
    training_run_id: str = "",
) -> ModelVersion:
    job = svc.submit_training_job(
        golden_job_spec(
            model_id=model_id,
            requested_version=version,
            idempotency_key=f"formal-{version}-{training_run_id or 'x'}",
            force_new=True,
        )
    )
    run_id = job.run_ids[0]
    run = svc.execute_training_run(run_id, inject=formal_inject())
    if run.status != "SUCCEEDED" or not run.model_version_id:
        raise ModelPlatformError(
            run.failure_reason or f"execute failed: {run.status}"
        )
    return svc.get_version(run.model_version_id)


__all__ = [
    "GOLDEN_CONFIG",
    "GOLDEN_DATASET_HASH",
    "GOLDEN_FEATURE_SET_HASH",
    "GOLDEN_FEATURE_SET_ID",
    "GOLDEN_LABEL_HASH",
    "GOLDEN_MODEL_CODE",
    "GOLDEN_SNAPSHOT_ID",
    "GOLDEN_VERSION",
    "advance_run_to_succeeded",
    "create_formal_version",
    "create_succeeded_run",
    "draft_stub_inject",
    "formal_inject",
    "golden_artifact_spec",
    "golden_job_spec",
    "golden_model_spec",
    "golden_training_run_spec",
    "golden_version_spec",
    "make_model_platform_env",
]
