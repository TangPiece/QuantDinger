"""Phase 9F-6：Model Evaluation 契约（独立于 ModelVersion 指标字段）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_model_evaluation@1"
EVALUATOR_VERSION = "qd_model_evaluator@1"
RUN_SCHEMA = "model_evaluation_run@1"
RESULT_SCHEMA = "model_evaluation_result@1"
POLICY_SCHEMA = "model_evaluation_policy@1"

RunStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "BLOCKED"]
LayerStatus = Literal["PASS", "WARNING", "FAIL", "BLOCKED", "SKIPPED"]


class _EvModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ModelEvaluationPolicy(_EvModel):
    schema_version: str = POLICY_SCHEMA
    policy_code: str = "MODEL_STANDARD_V1"
    version: str = "1.0.0"
    name: str = "Model Standard Evaluation"
    metrics: list[str] = Field(
        default_factory=lambda: [
            "mean_ic",
            "mean_rank_ic",
            "ic_ir",
            "ic_t_stat",
            "positive_ic_ratio",
            "precision_at_k",
            "hit_rate_at_k",
        ]
    )
    ranking_ks: list[int] = Field(default_factory=lambda: [10, 20, 50])
    missing_value_policy: str = "drop"
    min_cross_section: int = 3
    require_pit: bool = True
    benchmark: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelEvaluationRequest(_EvModel):
    model_version_id: str
    dataset_ref: str = ""
    evaluation_dataset_hash: str = ""
    dataset_hash: str = ""  # training lineage echo（可与 eval 不同）
    snapshot_id: str = ""
    feature_set_hash: str = ""
    label_hash: str = ""
    evaluation_start: str = ""
    evaluation_end: str = ""
    policy_code: str = "MODEL_STANDARD_V1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelMetric(_EvModel):
    name: str
    value: float | None = None
    status: LayerStatus = "PASS"
    detail: dict[str, Any] = Field(default_factory=dict)


class ModelEvaluationResult(_EvModel):
    schema_version: str = RESULT_SCHEMA
    engine_version: str = ENGINE_VERSION
    evaluation_run_id: str
    quality_status: LayerStatus = "PASS"
    predictive_status: LayerStatus = "SKIPPED"
    stability_status: LayerStatus = "SKIPPED"
    ranking_status: LayerStatus = "SKIPPED"
    overall_status: LayerStatus = "PASS"
    metrics: list[ModelMetric] = Field(default_factory=list)
    raw_metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ModelEvaluationRun(_EvModel):
    schema_version: str = RUN_SCHEMA
    engine_version: str = ENGINE_VERSION
    evaluation_run_id: str
    run_content_hash: str
    model_version_id: str
    dataset_hash: str = ""
    evaluation_dataset_hash: str = ""
    snapshot_id: str = ""
    feature_set_hash: str = ""
    label_hash: str = ""
    evaluation_policy_version: str = ""
    policy_content_hash: str = ""
    evaluator_version: str = EVALUATOR_VERSION
    evaluation_start: str = ""
    evaluation_end: str = ""
    status: RunStatus = "QUEUED"
    gate_reasons: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics_uri: str = ""
    prediction_uri: str = ""
    result: ModelEvaluationResult | None = None
    immutable: bool = True
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelEvaluationInject(_EvModel):
    """测试注入：跳过真实 predict / 提供预测面板。"""

    skip_immutability: bool = False
    known_hashes: dict[str, str] = Field(default_factory=dict)
    predictions: list[dict[str, Any]] = Field(default_factory=list)
    force_pit_fail: bool = False
    mark_evaluating: bool = False
    skip_artifact_check: bool = False


__all__ = [
    "ENGINE_VERSION",
    "EVALUATOR_VERSION",
    "LayerStatus",
    "ModelEvaluationInject",
    "ModelEvaluationPolicy",
    "ModelEvaluationRequest",
    "ModelEvaluationResult",
    "ModelEvaluationRun",
    "ModelMetric",
    "POLICY_SCHEMA",
    "RESULT_SCHEMA",
    "RUN_SCHEMA",
    "RunStatus",
]
