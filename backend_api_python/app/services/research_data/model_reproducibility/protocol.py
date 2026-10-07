"""Phase 9F-8：Reproducible Training 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_model_reproducibility@1"
MANIFEST_SCHEMA = "reproducibility_manifest@1"
INPUT_MANIFEST_SCHEMA = "training_input_manifest@1"
ENV_SCHEMA = "environment_fingerprint@1"
SEED_SCHEMA = "seed_bundle@1"
POLICY_SCHEMA = "reproducibility_policy@1"
RUN_SCHEMA = "reproducibility_run@1"
REPORT_SCHEMA = "reproducibility_report@1"

PolicyMode = Literal["STRICT", "REPRODUCIBLE", "AUDITABLE"]
RunStatus = Literal[
    "QUEUED",
    "PREPARING",
    "RUNNING",
    "COMPARING",
    "SUCCEEDED",
    "FAILED",
]
ReproResult = Literal[
    "EXACT_MATCH",
    "NUMERICAL_MATCH",
    "INPUT_MISMATCH",
    "CODE_MISMATCH",
    "ENV_MISMATCH",
    "DEPENDENCY_MISMATCH",
    "SEED_MISMATCH",
    "DATA_MISMATCH",
    "NON_DETERMINISTIC",
    "REPRODUCTION_FAILED",
    "AUDIT_OK",
]


class _RpModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PartitionEntry(_RpModel):
    uri: str
    checksum: str = ""
    rows: int = 0


class TrainingInputManifest(_RpModel):
    schema_version: str = INPUT_MANIFEST_SCHEMA
    dataset_hash: str = ""
    snapshot_id: str = ""
    partitions: list[PartitionEntry] = Field(default_factory=list)
    schema_hash: str = ""
    row_count: int = 0
    min_event_time: str = ""
    max_event_time: str = ""
    input_manifest_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnvironmentFingerprint(_RpModel):
    schema_version: str = ENV_SCHEMA
    python_version: str = ""
    os_name: str = ""
    os_version: str = ""
    architecture: str = ""
    cpu: str = ""
    gpu: str = ""
    cuda: str = ""
    cudnn: str = ""
    qlib_version: str = ""
    ml_framework: str = ""
    package_versions: dict[str, str] = Field(default_factory=dict)
    environment_variables: dict[str, str] = Field(default_factory=dict)
    container_image_digest: str = ""
    dependency_lock: dict[str, Any] = Field(default_factory=dict)
    dependency_lock_hash: str = ""
    environment_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SeedBundle(_RpModel):
    schema_version: str = SEED_SCHEMA
    master_seed: int = 0
    python_seed: int = 0
    numpy_seed: int = 0
    qlib_seed: int = 0
    framework_seed: int = 0
    model_seed: int = 0
    torch_seed: int | None = None
    torch_cuda_seed: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReproducibilityPolicy(_RpModel):
    schema_version: str = POLICY_SCHEMA
    policy_code: str = "REPRO_STRICT_V1"
    version: str = "1.0.0"
    name: str = "Reproducibility Strict V1"
    mode: PolicyMode = "STRICT"
    metric_tolerance: float = 1e-4
    prediction_tolerance: float = 1e-6
    artifact_match_required: bool = True
    environment_match_required: bool = True
    dependency_match_required: bool = True
    dataset_match_required: bool = True
    code_match_required: bool = True
    seed_match_required: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReproducibilityManifest(_RpModel):
    """TrainingRun 级不可变复现清单。"""

    schema_version: str = MANIFEST_SCHEMA
    engine_version: str = ENGINE_VERSION
    repro_manifest_id: str
    training_run_id: str
    model_id: str = ""
    model_version_id: str = ""
    dataset_hash: str = ""
    snapshot_id: str = ""
    feature_set_hash: str = ""
    factor_portfolio_hash: str = ""
    label_hash: str = ""
    processor_version: str = ""
    training_config_hash: str = ""
    hyperparameter_hash: str = ""
    model_adapter: str = ""
    model_adapter_version: str = ""
    framework: str = ""
    framework_version: str = ""
    code_version: str = ""
    code_commit: str = ""
    environment_hash: str = ""
    dependency_lock_hash: str = ""
    runtime_version: str = ""
    os_version: str = ""
    container_image_digest: str = ""
    random_seed: int = 0
    seeds: SeedBundle = Field(default_factory=SeedBundle)
    resource_config: dict[str, Any] = Field(default_factory=dict)
    deterministic_requested: bool = True
    deterministic_supported: bool = True
    deterministic_enabled: bool = True
    input_manifest: TrainingInputManifest = Field(default_factory=TrainingInputManifest)
    environment: EnvironmentFingerprint = Field(default_factory=EnvironmentFingerprint)
    artifact_id: str = ""
    artifact_checksum: str = ""
    metrics_snapshot: dict[str, Any] = Field(default_factory=dict)
    immutable: bool = True
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReproducibilityReport(_RpModel):
    schema_version: str = REPORT_SCHEMA
    engine_version: str = ENGINE_VERSION
    reproducibility_run_id: str
    result: ReproResult = "REPRODUCTION_FAILED"
    reason: str = ""
    input_match: bool = False
    code_match: bool = False
    environment_match: bool = False
    dependency_match: bool = False
    seed_match: bool = False
    artifact_match: bool = False
    metrics_within_tolerance: bool = False
    prediction_within_tolerance: bool = False
    metric_comparison: dict[str, Any] = Field(default_factory=dict)
    prediction_comparison: dict[str, Any] = Field(default_factory=dict)
    artifact_comparison: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ReproducibilityRun(_RpModel):
    schema_version: str = RUN_SCHEMA
    engine_version: str = ENGINE_VERSION
    reproducibility_run_id: str
    source_training_run_id: str
    reproduce_training_run_id: str = ""
    repro_manifest_id: str = ""
    repro_policy_version: str = ""
    policy_code: str = "REPRO_STRICT_V1"
    status: RunStatus = "QUEUED"
    result: ReproResult | str = ""
    reason: str = ""
    input_match: bool = False
    code_match: bool = False
    environment_match: bool = False
    dependency_match: bool = False
    seed_match: bool = False
    metric_comparison_uri: str = ""
    prediction_comparison_uri: str = ""
    artifact_comparison_uri: str = ""
    report_uri: str = ""
    report: ReproducibilityReport | None = None
    immutable: bool = True
    created_at: datetime
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReproducibilityInject(_RpModel):
    """单测注入：篡改条件 / 钉比较输入 / 跳过真实训练。"""

    known_partitions: list[dict[str, Any]] = Field(default_factory=list)
    dependency_lock: dict[str, Any] = Field(default_factory=dict)
    package_versions: dict[str, str] = Field(default_factory=dict)
    code_commit: str = ""
    container_image_digest: str = ""
    mutate_dataset_hash: str = ""
    mutate_snapshot_id: str = ""
    mutate_feature_set_hash: str = ""
    mutate_processor_version: str = ""
    mutate_partition_checksum: str = ""
    mutate_code_commit: str = ""
    mutate_dependency_lock_hash: str = ""
    mutate_environment_hash: str = ""
    mutate_seed: int | None = None
    predictions_original: list[dict[str, Any]] = Field(default_factory=list)
    predictions_reproduced: list[dict[str, Any]] = Field(default_factory=list)
    metrics_original: dict[str, Any] = Field(default_factory=dict)
    metrics_reproduced: dict[str, Any] = Field(default_factory=dict)
    artifact_checksum_original: str = ""
    artifact_checksum_reproduced: str = ""
    deterministic_requested: bool | None = None
    deterministic_supported: bool | None = None
    deterministic_enabled: bool | None = None
    skip_execute: bool = False
    skip_capture_immutability: bool = False
    force_non_deterministic: bool = False


__all__ = [
    "ENGINE_VERSION",
    "ENV_SCHEMA",
    "INPUT_MANIFEST_SCHEMA",
    "MANIFEST_SCHEMA",
    "POLICY_SCHEMA",
    "REPORT_SCHEMA",
    "RUN_SCHEMA",
    "SEED_SCHEMA",
    "EnvironmentFingerprint",
    "PartitionEntry",
    "PolicyMode",
    "ReproResult",
    "ReproducibilityInject",
    "ReproducibilityManifest",
    "ReproducibilityPolicy",
    "ReproducibilityReport",
    "ReproducibilityRun",
    "RunStatus",
    "SeedBundle",
    "TrainingInputManifest",
]
