"""Model / Version / TrainingRun / Artifact 引用与 R2 键。"""

from __future__ import annotations

import uuid

from app.services.research_data import config as rd_config


def new_model_id() -> str:
    return f"mdl_{uuid.uuid4().hex[:16]}"


def new_model_version_id() -> str:
    return f"mver_{uuid.uuid4().hex[:16]}"


def new_training_run_id() -> str:
    return f"trun_{uuid.uuid4().hex[:16]}"


def new_training_job_id() -> str:
    return f"tjob_{uuid.uuid4().hex[:16]}"


def new_artifact_id() -> str:
    return f"mart_{uuid.uuid4().hex[:16]}"


def model_key(*, model_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/model_platform/models/{model_id}.json"


def model_version_key(*, model_version_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/model_platform/versions/{model_version_id}.json"


def training_run_key(*, training_run_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/model_platform/training_runs/{training_run_id}.json"


def training_job_key(*, job_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/model_platform/training_jobs/{job_id}.json"


def model_artifact_key(*, artifact_id: str) -> str:
    root = rd_config.canonical_prefix()
    return f"{root}/model_platform/artifacts/{artifact_id}.json"


def model_version_ref(*, model_code: str, version: str) -> str:
    return f"{model_code}@{version}"


__all__ = [
    "model_artifact_key",
    "model_key",
    "model_version_key",
    "model_version_ref",
    "new_artifact_id",
    "new_model_id",
    "new_model_version_id",
    "new_training_job_id",
    "new_training_run_id",
    "training_job_key",
    "training_run_key",
]
