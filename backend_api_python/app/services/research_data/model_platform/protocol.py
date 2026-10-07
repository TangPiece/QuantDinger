"""Phase 9F-1：Model Platform 契约（Registry / Version / TrainingRun / Artifact）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_model_platform@1"
MODEL_SCHEMA = "model@1"
MODEL_VERSION_SCHEMA = "model_version@1"
TRAINING_RUN_SCHEMA = "training_run@1"
TRAINING_JOB_SCHEMA = "training_job@1"
MODEL_ARTIFACT_SCHEMA = "model_artifact@1"
MODEL_APPROVAL_SCHEMA = "model_approval@1"
MODEL_APPROVAL_POLICY_SCHEMA = "model_approval_policy@1"
MODEL_ACTIVATION_SCHEMA = "model_activation@1"

DEFAULT_USAGE_SCOPE: list[str] = ["RESEARCH", "EXPERIMENT", "BACKTEST"]

ModelType = Literal[
    "REGRESSION",
    "CLASSIFICATION",
    "RANKING",
    "TIME_SERIES",
    "DEEP_LEARNING",
    "ENSEMBLE",
    "CUSTOM",
]

ModelStatus = Literal["ACTIVE", "INACTIVE", "ARCHIVED"]

ModelVersionLifecycle = Literal[
    "DRAFT",
    "TRAINING",
    "TRAINED",
    "EVALUATING",
    "VALIDATED",
    "APPROVED",
    "ACTIVE",
    "DEPRECATED",
    "RETIRED",
]

TrainingRunStatus = Literal[
    "QUEUED",
    "PREPARING",
    "RUNNING",
    "FINALIZING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
]

TrainingJobStatus = Literal["OPEN", "CLOSED"]

ArtifactStatus = Literal[
    "CREATING",
    "UPLOADING",
    "VERIFYING",
    "AVAILABLE",
    "FAILED",
    "CORRUPTED",
]

FailureClass = Literal[
    "DATA_ERROR",
    "DATA_MISSING",
    "DATA_CORRUPTED",
    "FEATURE_ERROR",
    "LABEL_ERROR",
    "PROCESSOR_ERROR",
    "CONFIG_ERROR",
    "MODEL_ERROR",
    "RESOURCE_ERROR",
    "TIMEOUT",
    "ARTIFACT_ERROR",
    "SYSTEM_ERROR",
    "CANCELLED",
]

ApprovalDecision = Literal["APPROVED", "REJECTED", "REVOKED"]

DeprecateReason = Literal[
    "PERFORMANCE_DEGRADATION",
    "DATA_ISSUE",
    "MODEL_ISSUE",
    "NEW_VERSION",
    "SECURITY_ISSUE",
    "RESEARCH_DECISION",
    "OTHER",
]

UsageScope = Literal[
    "RESEARCH",
    "EXPERIMENT",
    "BACKTEST",
    "PAPER",
    "PRODUCTION",
]


class _PlatformModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ModelSpec(_PlatformModel):
    """register_model 输入。"""

    model_code: str
    name: str
    description: str = ""
    model_type: ModelType = "REGRESSION"
    framework: str = "CUSTOM"
    owner: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Model(_PlatformModel):
    """逻辑模型资产（≠ ModelVersion）。"""

    schema_version: str = MODEL_SCHEMA
    engine_version: str = ENGINE_VERSION
    model_id: str
    model_code: str
    name: str
    description: str = ""
    model_type: ModelType = "REGRESSION"
    framework: str = "CUSTOM"
    owner: str = ""
    status: ModelStatus = "ACTIVE"
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelVersionSpec(_PlatformModel):
    """register_version 输入。"""

    version: str
    dataset_hash: str = ""
    snapshot_id: str = ""
    feature_set_id: str = ""
    feature_set_hash: str = ""
    factor_portfolio_id: str = ""
    factor_portfolio_version: str = ""
    label_id: str = ""
    label_hash: str = ""
    processor_version: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    framework: str = ""
    framework_version: str = ""
    code_version: str = ""
    environment_hash: str = ""
    random_seed: int = 0
    training_run_id: str = ""
    artifact_id: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelVersion(_PlatformModel):
    """可复现的模型版本（钉 lineage hashes）。"""

    schema_version: str = MODEL_VERSION_SCHEMA
    engine_version: str = ENGINE_VERSION
    model_version_id: str
    model_id: str
    model_code: str
    version: str
    version_content_hash: str
    lifecycle: ModelVersionLifecycle = "DRAFT"
    dataset_hash: str = ""
    snapshot_id: str = ""
    feature_set_id: str = ""
    feature_set_hash: str = ""
    factor_portfolio_id: str = ""
    factor_portfolio_version: str = ""
    label_id: str = ""
    label_hash: str = ""
    processor_version: str = ""
    model_config_hash: str = ""
    hyperparameter_hash: str = ""
    framework: str = ""
    framework_version: str = ""
    code_version: str = ""
    environment_hash: str = ""
    random_seed: int = 0
    training_run_id: str = ""
    artifact_id: str = ""
    deprecate_reason: str = ""
    deprecate_reason_code: str = ""
    replacement_ref: str = ""
    usage_scope: list[str] = Field(default_factory=lambda: list(DEFAULT_USAGE_SCOPE))
    immutable: bool = True
    created_at: datetime
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrainingConfig(_PlatformModel):
    """标准化训练配置（→ training_config_hash）。"""

    algorithm: str = "lightgbm"
    objective: str = "regression"
    parameters: dict[str, Any] = Field(default_factory=dict)
    early_stopping: dict[str, Any] = Field(default_factory=dict)
    num_boost_round: int = 100


class ResourceConfig(_PlatformModel):
    executor: str = "local"
    cpu: int = 1
    memory_mb: int = 1024
    gpu: int = 0
    threads: int = 1


class TrainingJobSpec(_PlatformModel):
    """submit_training_job 输入。"""

    model_id: str = ""
    model_code: str = ""
    requested_version: str = ""
    dataset_ref: str = ""
    dataset_hash: str = ""
    snapshot_id: str = ""
    feature_set_id: str = ""
    feature_set_hash: str = ""
    factor_portfolio_hash: str = ""
    label_hash: str = ""
    processor_version: str = ""
    training_config: dict[str, Any] = Field(default_factory=dict)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    resource_config: dict[str, Any] = Field(default_factory=dict)
    framework: str = ""
    framework_version: str = ""
    code_version: str = ""
    environment_hash: str = ""
    random_seed: int = 0
    train_start: str = ""
    train_end: str = ""
    validation_start: str = ""
    validation_end: str = ""
    idempotency_key: str = ""
    force_new: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrainingJob(_PlatformModel):
    """训练意图（可含多次 TrainingRun 重试）。"""

    schema_version: str = TRAINING_JOB_SCHEMA
    engine_version: str = ENGINE_VERSION
    job_id: str
    model_id: str = ""
    model_code: str = ""
    requested_version: str = ""
    dataset_ref: str = ""
    dataset_hash: str = ""
    snapshot_id: str = ""
    feature_set_id: str = ""
    feature_set_hash: str = ""
    factor_portfolio_hash: str = ""
    label_hash: str = ""
    processor_version: str = ""
    training_config: dict[str, Any] = Field(default_factory=dict)
    training_config_hash: str = ""
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    resource_config: dict[str, Any] = Field(default_factory=dict)
    framework: str = ""
    framework_version: str = ""
    code_version: str = ""
    environment_hash: str = ""
    random_seed: int = 0
    train_start: str = ""
    train_end: str = ""
    validation_start: str = ""
    validation_end: str = ""
    idempotency_key: str = ""
    status: TrainingJobStatus = "OPEN"
    run_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrainingRunSpec(_PlatformModel):
    """create_training_run 输入（仅 pin，不执行训练）。"""

    training_run_id: str = ""
    job_id: str = ""
    model_id: str = ""
    model_code: str = ""
    model_version_id: str = ""
    requested_model_version: str = ""
    dataset_ref: str = ""
    dataset_hash: str = ""
    snapshot_id: str = ""
    feature_set_id: str = ""
    feature_set_hash: str = ""
    factor_portfolio_hash: str = ""
    label_hash: str = ""
    processor_version: str = ""
    train_start: str = ""
    train_end: str = ""
    validation_start: str = ""
    validation_end: str = ""
    random_seed: int = 0
    training_config: dict[str, Any] = Field(default_factory=dict)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    resource_config: dict[str, Any] = Field(default_factory=dict)
    framework: str = ""
    framework_version: str = ""
    code_version: str = ""
    environment_hash: str = ""
    status: TrainingRunStatus = "QUEUED"
    parent_training_run_id: str = ""
    retry_index: int = 0
    idempotency_key: str = ""
    logs_uri: str = ""
    metrics_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrainingRun(_PlatformModel):
    """训练过程记录（一次实际执行）。"""

    schema_version: str = TRAINING_RUN_SCHEMA
    engine_version: str = ENGINE_VERSION
    training_run_id: str
    training_run_hash: str
    job_id: str = ""
    model_id: str = ""
    model_code: str = ""
    model_version_id: str = ""
    requested_model_version: str = ""
    dataset_ref: str = ""
    dataset_hash: str = ""
    snapshot_id: str = ""
    feature_set_id: str = ""
    feature_set_hash: str = ""
    factor_portfolio_hash: str = ""
    label_hash: str = ""
    processor_version: str = ""
    train_start: str = ""
    train_end: str = ""
    validation_start: str = ""
    validation_end: str = ""
    random_seed: int = 0
    training_config: dict[str, Any] = Field(default_factory=dict)
    training_config_hash: str = ""
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    hyperparameter_hash: str = ""
    resource_config: dict[str, Any] = Field(default_factory=dict)
    framework: str = ""
    framework_version: str = ""
    code_version: str = ""
    environment_hash: str = ""
    status: TrainingRunStatus = "QUEUED"
    failure_class: str = ""
    failure_reason: str = ""
    failure_detail: str = ""
    parent_training_run_id: str = ""
    retry_index: int = 0
    idempotency_key: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    lineage_frozen: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    logs_uri: str = ""
    metrics_uri: str = ""
    immutable: bool = True
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelArtifactSpec(_PlatformModel):
    """register_artifact / put 输入（索引 + 可选 payload 引用）。"""

    model_version_id: str = ""
    artifact_type: str = "MODEL"
    artifact_uri: str = ""
    file_size: int = 0
    checksum: str = ""
    checksum_algorithm: str = "SHA256"
    content_type: str = "application/octet-stream"
    framework: str = ""
    framework_version: str = ""
    producer_type: str = ""
    producer_id: str = ""
    feature_schema_uri: str = ""
    processor_uri: str = ""
    label_definition_uri: str = ""
    environment_uri: str = ""
    training_metadata_uri: str = ""
    manifest_uri: str = ""
    metadata_uri: str = ""
    status: ArtifactStatus = "CREATING"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelArtifact(_PlatformModel):
    """模型 Artifact 索引（二进制在 qd/artifacts/model/{id}/）。"""

    schema_version: str = MODEL_ARTIFACT_SCHEMA
    engine_version: str = ENGINE_VERSION
    artifact_id: str
    model_version_id: str = ""
    artifact_type: str = "MODEL"
    artifact_uri: str = ""
    file_size: int = 0
    checksum: str = ""
    checksum_algorithm: str = "SHA256"
    content_type: str = "application/octet-stream"
    framework: str = ""
    framework_version: str = ""
    producer_type: str = ""
    producer_id: str = ""
    feature_schema_uri: str = ""
    processor_uri: str = ""
    label_definition_uri: str = ""
    environment_uri: str = ""
    training_metadata_uri: str = ""
    manifest_uri: str = ""
    metadata_uri: str = ""
    status: ArtifactStatus = "CREATING"
    immutable: bool = True
    created_at: datetime
    immutable_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelSearchQuery(_PlatformModel):
    """目录检索。"""

    model_code_prefix: str = ""
    model_type: list[ModelType] = Field(default_factory=list)
    framework: str = ""
    lifecycle: list[ModelVersionLifecycle] = Field(default_factory=list)
    tags_any: list[str] = Field(default_factory=list)
    tags_all: list[str] = Field(default_factory=list)
    text: str = ""


class ModelApprovalPolicy(_PlatformModel):
    """审批策略（阈值与整体状态白名单）。"""

    schema_version: str = MODEL_APPROVAL_POLICY_SCHEMA
    policy_code: str = "MODEL_APPROVAL_V1"
    version: str = "1.0.0"
    name: str = "Model Approval V1"
    allowed_overall_status: list[str] = Field(default_factory=lambda: ["PASS"])
    require_eval_succeeded: bool = True
    require_artifact_available: bool = True
    require_lineage_hashes: bool = True
    require_pit: bool = True
    min_mean_ic: float | None = None
    min_mean_rank_ic: float | None = None
    min_ic_ir: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelApproval(_PlatformModel):
    """不可变审批审计（仅追加）。"""

    schema_version: str = MODEL_APPROVAL_SCHEMA
    engine_version: str = ENGINE_VERSION
    approval_id: str
    model_id: str
    model_version_id: str
    evaluation_run_id: str = ""
    approval_policy_version: str = "MODEL_APPROVAL_V1@1.0.0"
    decision: ApprovalDecision
    reason: str = ""
    operator: str = ""
    approved_at: datetime | None = None
    created_at: datetime
    gate_dump: dict[str, Any] = Field(default_factory=dict)
    immutable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelActivationRecord(_PlatformModel):
    """ACTIVE 切换审计（仅追加）。"""

    schema_version: str = MODEL_ACTIVATION_SCHEMA
    engine_version: str = ENGINE_VERSION
    activation_id: str
    model_id: str
    from_model_version_id: str = ""
    to_model_version_id: str
    reason: str = ""
    operator: str = ""
    policy_version: str = "MODEL_APPROVAL_V1@1.0.0"
    created_at: datetime
    immutable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalGateResult(_PlatformModel):
    """ApprovalGate 输出。"""

    verdict: Literal["PASS", "REJECT"] = "REJECT"
    reasons: list[str] = Field(default_factory=list)
    evaluation_run_id: str = ""
    overall_status: str = ""
    policy_version: str = ""
    artifact_id: str = ""
    metrics_snapshot: dict[str, Any] = Field(default_factory=dict)


class ModelPlatformInject(_PlatformModel):
    """测试注入。"""

    skip_immutability: bool = False
    auto_activate: bool = False
    allow_draft_stub: bool = False
    known_hashes: dict[str, str] = Field(default_factory=dict)
    expected_checksum: str = ""
    simulate_fail_at: str = ""
    simulate_cancel: bool = False
    skip_create_version: bool = False
    feature_set_id: str = ""
    label_hash: str = ""
    processor_version: str = ""
    snapshot_id: str = ""
    # 9F-4：注入 DataQuery 侧已解析的 dataset_hash（无 registry 时跳过 live 校验）
    skip_dataset_ref_check: bool = False
    # 9F-7：仅单测可跳过 ApprovalGate（禁止产品化静默绕过）
    skip_approval_gate: bool = False


__all__ = [
    "ENGINE_VERSION",
    "ApprovalDecision",
    "ApprovalGateResult",
    "ArtifactStatus",
    "DEFAULT_USAGE_SCOPE",
    "DeprecateReason",
    "FailureClass",
    "MODEL_ACTIVATION_SCHEMA",
    "MODEL_APPROVAL_POLICY_SCHEMA",
    "MODEL_APPROVAL_SCHEMA",
    "MODEL_ARTIFACT_SCHEMA",
    "MODEL_SCHEMA",
    "MODEL_VERSION_SCHEMA",
    "Model",
    "ModelActivationRecord",
    "ModelApproval",
    "ModelApprovalPolicy",
    "ModelArtifact",
    "ModelArtifactSpec",
    "ModelPlatformInject",
    "ModelSearchQuery",
    "ModelSpec",
    "ModelStatus",
    "ModelType",
    "ModelVersion",
    "ModelVersionLifecycle",
    "ModelVersionSpec",
    "ResourceConfig",
    "TRAINING_JOB_SCHEMA",
    "TRAINING_RUN_SCHEMA",
    "TrainingConfig",
    "TrainingJob",
    "TrainingJobSpec",
    "TrainingJobStatus",
    "TrainingRun",
    "TrainingRunSpec",
    "TrainingRunStatus",
    "UsageScope",
]
