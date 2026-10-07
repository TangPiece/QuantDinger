"""Phase 9F-1 Model Platform golden 环境。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.research_data.model_platform.protocol import (
    ModelArtifactSpec,
    ModelSpec,
    ModelVersionSpec,
    TrainingRunSpec,
)
from app.services.research_data.model_platform.runner import ModelPlatformService

GOLDEN_MODEL_CODE = "alpha_lgb_ranker"
GOLDEN_VERSION = "1.0.0"
GOLDEN_DATASET_HASH = "d" * 64
GOLDEN_FEATURE_SET_HASH = "f" * 64
GOLDEN_CONFIG = {
    "objective": "regression",
    "learning_rate": 0.03,
    "num_leaves": 64,
    "seed": 42,
}


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
        "snapshot_id": "snap_golden",
        "feature_set_hash": GOLDEN_FEATURE_SET_HASH,
        "label_hash": "l" * 64,
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
        "dataset_hash": GOLDEN_DATASET_HASH,
        "feature_set_hash": GOLDEN_FEATURE_SET_HASH,
        "train_start": "2020-01-01",
        "train_end": "2020-06-30",
        "validation_start": "2020-07-01",
        "validation_end": "2020-09-30",
        "random_seed": 42,
        "hyperparameters": {"num_boost_round": 100},
        "status": "QUEUED",
    }
    data.update(kwargs)
    return TrainingRunSpec.model_validate(data)


def golden_artifact_spec(model_version_id: str, **kwargs: Any) -> ModelArtifactSpec:
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


__all__ = [
    "GOLDEN_CONFIG",
    "GOLDEN_DATASET_HASH",
    "GOLDEN_FEATURE_SET_HASH",
    "GOLDEN_MODEL_CODE",
    "GOLDEN_VERSION",
    "golden_artifact_spec",
    "golden_model_spec",
    "golden_training_run_spec",
    "golden_version_spec",
    "make_model_platform_env",
]
