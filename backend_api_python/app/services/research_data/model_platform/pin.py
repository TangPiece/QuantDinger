"""钉住 Model / ModelVersion / TrainingRun / Artifact。"""

from __future__ import annotations

from datetime import datetime, timezone
from .hashing import (
    compute_hyperparameter_hash,
    compute_model_config_hash,
    compute_training_run_hash,
    compute_version_content_hash,
)
from .identity import (
    new_artifact_id,
    new_model_id,
    new_model_version_id,
    new_training_run_id,
)
from .protocol import (
    ENGINE_VERSION,
    Model,
    ModelArtifact,
    ModelArtifactSpec,
    ModelSpec,
    ModelStatus,
    ModelVersion,
    ModelVersionLifecycle,
    ModelVersionSpec,
    TrainingRun,
    TrainingRunSpec,
)
from .taxonomy import normalize_model_type, normalize_tags


def pin_model(
    spec: ModelSpec,
    *,
    model_id: str | None = None,
    status: ModelStatus = "ACTIVE",
    created_at: datetime | None = None,
) -> Model:
    ts = created_at or datetime.now(timezone.utc)
    return Model(
        engine_version=ENGINE_VERSION,
        model_id=model_id or new_model_id(),
        model_code=spec.model_code,
        name=spec.name,
        description=spec.description,
        model_type=normalize_model_type(spec.model_type),
        framework=str(spec.framework or "CUSTOM").upper(),
        owner=spec.owner,
        status=status,
        tags=normalize_tags(spec.tags),
        created_at=ts,
        updated_at=ts,
        metadata=dict(spec.metadata or {}),
    )


def pin_model_version(
    *,
    model_id: str,
    model_code: str,
    spec: ModelVersionSpec,
    model_version_id: str | None = None,
    lifecycle: ModelVersionLifecycle = "DRAFT",
    created_at: datetime | None = None,
) -> ModelVersion:
    ts = created_at or datetime.now(timezone.utc)
    cfg_hash = compute_model_config_hash(spec.config)
    hp_hash = compute_hyperparameter_hash(spec.hyperparameters)
    framework = str(spec.framework or "").upper()
    vhash = compute_version_content_hash(
        model_code=model_code,
        version=spec.version,
        dataset_hash=spec.dataset_hash,
        snapshot_id=spec.snapshot_id,
        feature_set_hash=spec.feature_set_hash,
        factor_portfolio_id=spec.factor_portfolio_id,
        factor_portfolio_version=spec.factor_portfolio_version,
        label_hash=spec.label_hash,
        processor_version=spec.processor_version,
        model_config_hash=cfg_hash,
        hyperparameter_hash=hp_hash,
        framework=framework,
        framework_version=spec.framework_version,
        code_version=spec.code_version,
        environment_hash=spec.environment_hash,
        random_seed=spec.random_seed,
    )
    meta = dict(spec.metadata or {})
    if spec.config:
        meta["config"] = dict(spec.config)
    if spec.hyperparameters:
        meta["hyperparameters"] = dict(spec.hyperparameters)
    return ModelVersion(
        engine_version=ENGINE_VERSION,
        model_version_id=model_version_id or new_model_version_id(),
        model_id=model_id,
        model_code=model_code,
        version=spec.version,
        version_content_hash=vhash,
        lifecycle=lifecycle,
        dataset_hash=spec.dataset_hash,
        snapshot_id=spec.snapshot_id,
        feature_set_id=spec.feature_set_id,
        feature_set_hash=spec.feature_set_hash,
        factor_portfolio_id=spec.factor_portfolio_id,
        factor_portfolio_version=spec.factor_portfolio_version,
        label_id=spec.label_id,
        label_hash=spec.label_hash,
        processor_version=spec.processor_version,
        model_config_hash=cfg_hash,
        hyperparameter_hash=hp_hash,
        framework=framework,
        framework_version=spec.framework_version,
        code_version=spec.code_version,
        environment_hash=spec.environment_hash,
        random_seed=spec.random_seed,
        training_run_id=spec.training_run_id,
        artifact_id=spec.artifact_id,
        tags=normalize_tags(spec.tags),
        created_at=ts,
        metadata=meta,
    )


def pin_training_run(
    spec: TrainingRunSpec,
    *,
    training_run_id: str | None = None,
    created_at: datetime | None = None,
) -> TrainingRun:
    ts = created_at or datetime.now(timezone.utc)
    rid = training_run_id or (spec.training_run_id or "") or new_training_run_id()
    thash = compute_training_run_hash(
        model_id=spec.model_id,
        model_version_id=spec.model_version_id,
        dataset_hash=spec.dataset_hash,
        feature_set_hash=spec.feature_set_hash,
        factor_portfolio_hash=spec.factor_portfolio_hash,
        train_start=spec.train_start,
        train_end=spec.train_end,
        validation_start=spec.validation_start,
        validation_end=spec.validation_end,
        random_seed=spec.random_seed,
        hyperparameters=spec.hyperparameters,
    )
    return TrainingRun(
        engine_version=ENGINE_VERSION,
        training_run_id=rid,
        training_run_hash=thash,
        model_id=spec.model_id,
        model_code=spec.model_code,
        model_version_id=spec.model_version_id,
        dataset_hash=spec.dataset_hash,
        feature_set_hash=spec.feature_set_hash,
        factor_portfolio_hash=spec.factor_portfolio_hash,
        train_start=spec.train_start,
        train_end=spec.train_end,
        validation_start=spec.validation_start,
        validation_end=spec.validation_end,
        random_seed=spec.random_seed,
        hyperparameters=dict(spec.hyperparameters or {}),
        resource_config=dict(spec.resource_config or {}),
        status=spec.status,
        logs_uri=spec.logs_uri,
        metrics_uri=spec.metrics_uri,
        created_at=ts,
        metadata=dict(spec.metadata or {}),
    )


def pin_model_artifact(
    spec: ModelArtifactSpec,
    *,
    artifact_id: str | None = None,
    created_at: datetime | None = None,
) -> ModelArtifact:
    ts = created_at or datetime.now(timezone.utc)
    return ModelArtifact(
        engine_version=ENGINE_VERSION,
        artifact_id=artifact_id or new_artifact_id(),
        model_version_id=spec.model_version_id,
        artifact_type=spec.artifact_type,
        artifact_uri=spec.artifact_uri,
        file_size=int(spec.file_size or 0),
        checksum=spec.checksum,
        framework=str(spec.framework or "").upper(),
        framework_version=spec.framework_version,
        feature_schema_uri=spec.feature_schema_uri,
        processor_uri=spec.processor_uri,
        label_definition_uri=spec.label_definition_uri,
        environment_uri=spec.environment_uri,
        training_metadata_uri=spec.training_metadata_uri,
        created_at=ts,
        metadata=dict(spec.metadata or {}),
    )


__all__ = [
    "pin_model",
    "pin_model_artifact",
    "pin_model_version",
    "pin_training_run",
]
