"""Phase 9C：Factor Evaluation Platform 契约（Policy / Run / Gate）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_evaluation_platform@1"
EVALUATION_RUN_INDEX_SCHEMA = "evaluation_run_index@1"
QUALITY_SCORE_SCHEMA = "factor_quality_score@1"

RunStatus = Literal["SUCCESS", "BLOCKED"]
QualityGateVerdict = Literal["PASS", "BLOCKED"]


class _PlatformModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class QualityGateResult(_PlatformModel):
    verdict: QualityGateVerdict = "PASS"
    reasons: list[str] = Field(default_factory=list)


class FactorEvaluationRequest(_PlatformModel):
    """run_evaluation 输入视图（hash 与审计）。"""

    factor_ref: str
    dataset_ref: str
    policy_id: str = "default_equity_factor_v1"
    start_date: str
    end_date: str
    layout: Literal["long", "wide"] = "long"


class EvaluationRun(_PlatformModel):
    """单次评价运行（门面返回）。"""

    evaluation_id: str
    run_content_hash: str
    status: RunStatus
    factor_ref: str
    factor_hash: str
    dataset_ref: str
    dataset_hash: str
    factor_dataset_id: str = ""
    policy_id: str
    policy_content_hash: str
    evaluation_policy_version: str = "1.0.0"
    engine_version: str = ENGINE_VERSION
    start_date: str
    end_date: str
    evaluation_hash: str = ""
    metric_hash: str = ""
    group_evaluation_hash: str = ""
    stability_hash: str = ""
    resolved_direction: str = ""
    gate_verdict: QualityGateVerdict = "PASS"
    gate_reasons: list[str] = Field(default_factory=list)
    quality_score_uri: str = ""
    published_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationRunIndex(_PlatformModel):
    """不可变 EvaluationRun 索引（LocalJson / R2 镜像）。"""

    schema_version: str = EVALUATION_RUN_INDEX_SCHEMA
    engine_version: str = ENGINE_VERSION
    evaluation_id: str
    run_content_hash: str
    status: RunStatus
    factor_ref: str
    factor_hash: str
    dataset_ref: str
    dataset_hash: str
    factor_dataset_id: str = ""
    policy_id: str
    policy_content_hash: str
    evaluation_policy_version: str = "1.0.0"
    start_date: str
    end_date: str
    evaluation_hash: str = ""
    metric_hash: str = ""
    group_evaluation_hash: str = ""
    stability_hash: str = ""
    resolved_direction: str = ""
    gate_verdict: QualityGateVerdict = "PASS"
    gate_reasons: list[str] = Field(default_factory=list)
    quality_score_uri: str = ""
    immutable: bool = True
    published_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorQualityScore(_PlatformModel):
    """薄层质量分：索引用；raw 指标必须保留。"""

    schema_version: str = QUALITY_SCORE_SCHEMA
    engine_version: str = ENGINE_VERSION
    evaluation_id: str
    run_content_hash: str
    total_score: float
    ic_score: float = 0.0
    icir_score: float = 0.0
    stability_score: float = 0.0
    turnover_score: float = 0.0
    cost_score: float = 0.0
    raw_metrics: dict[str, Any] = Field(default_factory=dict)
    published_at: datetime


class LineageNode(_PlatformModel):
    ref: str
    kind: str
    hash_value: str = ""
    children: list["LineageNode"] = Field(default_factory=list)


LineageNode.model_rebuild()


class EvaluationPlatformInject(_PlatformModel):
    """Fake golden 注入：gate / 4C–4F metadata / 策略覆盖。"""

    gate_override: dict[str, Any] | None = None
    skip_immutability: bool = False
    skip_build_resolve: bool = False
    build_index_payload: dict[str, Any] | None = None
    lab_metadata: dict[str, Any] | None = None
    policy_overrides: dict[str, Any] | None = None


__all__ = [
    "ENGINE_VERSION",
    "EVALUATION_RUN_INDEX_SCHEMA",
    "EvaluationPlatformInject",
    "EvaluationRun",
    "EvaluationRunIndex",
    "FactorEvaluationRequest",
    "FactorQualityScore",
    "LineageNode",
    "QualityGateResult",
    "QualityGateVerdict",
    "RunStatus",
]
