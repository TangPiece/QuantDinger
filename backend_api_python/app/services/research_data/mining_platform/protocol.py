"""Phase 9D：Factor Mining Platform 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_mining_platform@1"
MINING_RUN_INDEX_SCHEMA = "mining_run_index@1"
MINING_CANDIDATE_SCHEMA = "factor_candidate@1"
MINING_SCORE_SCHEMA = "mining_score@1"

MiningRunStatus = Literal[
    "CREATED",
    "RUNNING",
    "SCREENING",
    "EVALUATING",
    "RANKING",
    "COMPLETED",
    "FAILED",
]
GeneratorStrategy = Literal["exhaustive_small", "random_search"]
CandidateStatus = Literal[
    "GENERATED",
    "SCREENED_OUT",
    "DEDUP_REMOVED",
    "REDUNDANT",
    "EVALUATED",
    "RANKED",
    "FAILED",
]


class _PlatformModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MiningJob(_PlatformModel):
    """run_mining 输入。"""

    dataset_ref: str
    feature_set_ref: str = ""
    feature_columns: list[str] = Field(default_factory=list)
    mining_policy_id: str = "default_mining_small_v1"
    evaluation_policy_id: str = "default_equity_factor_v1"
    random_seed: int
    train_start: str
    train_end: str
    validation_start: str = ""
    validation_end: str = ""
    holdout_start: str = ""
    holdout_end: str = ""
    layout: Literal["long", "wide"] = "long"


class FactorCandidate(_PlatformModel):
    """单次挖掘候选（不自动 APPROVED）。"""

    schema_version: str = MINING_CANDIDATE_SCHEMA
    candidate_id: str
    mining_run_id: str
    expression_hash: str
    dsl_expression: str
    depth: int = 1
    status: CandidateStatus = "GENERATED"
    factor_ref: str = ""
    evaluation_id: str = ""
    holdout_evaluation_id: str = ""
    holdout_metrics: dict[str, Any] = Field(default_factory=dict)
    mining_score: float = 0.0
    redundant_with: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class MiningScore(_PlatformModel):
    """挖掘排序分（≠ 9C QualityScore；holdout 不参与）。"""

    schema_version: str = MINING_SCORE_SCHEMA
    engine_version: str = ENGINE_VERSION
    candidate_id: str
    mining_run_id: str
    rank: int = 0
    selection_score: float = 0.0
    ic_score: float = 0.0
    quality_total: float = 0.0
    raw: dict[str, Any] = Field(default_factory=dict)
    published_at: datetime


class MiningRun(_PlatformModel):
    """门面返回的挖掘运行。"""

    mining_run_id: str
    mining_run_hash: str
    status: MiningRunStatus
    dataset_ref: str
    dataset_hash: str
    feature_set_hash: str
    mining_policy_id: str
    mining_policy_content_hash: str
    evaluation_policy_id: str
    evaluation_policy_version: str = "1.0.0"
    random_seed: int
    engine_version: str = ENGINE_VERSION
    total_candidates_generated: int = 0
    total_candidates_screened: int = 0
    total_candidates_tested: int = 0
    total_survivors: int = 0
    selection_bias_warning: str = ""
    candidates: list[FactorCandidate] = Field(default_factory=list)
    published_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class MiningRunIndex(_PlatformModel):
    """不可变 MiningRun 索引。"""

    schema_version: str = MINING_RUN_INDEX_SCHEMA
    engine_version: str = ENGINE_VERSION
    mining_run_id: str
    mining_run_hash: str
    status: MiningRunStatus
    dataset_ref: str
    dataset_hash: str
    feature_set_hash: str
    mining_policy_id: str
    mining_policy_content_hash: str
    evaluation_policy_id: str
    evaluation_policy_version: str = "1.0.0"
    random_seed: int
    total_candidates_generated: int = 0
    total_candidates_screened: int = 0
    total_candidates_tested: int = 0
    total_survivors: int = 0
    selection_bias_warning: str = ""
    candidate_ids: list[str] = Field(default_factory=list)
    immutable: bool = True
    published_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class MiningPlatformInject(_PlatformModel):
    """Fake golden 注入：跳过重计算 / 固定 IC / corr。"""

    skip_immutability: bool = False
    skip_build_eval: bool = False
    screen_ic_threshold: float | None = None
    fast_screen_pass_all: bool = False
    dedup_corr_threshold: float | None = None
    corr_pairs_redundant: list[tuple[str, str]] | None = None
    evaluation_inject: dict[str, Any] | None = None
    holdout_metrics_by_expression_hash: dict[str, dict[str, Any]] | None = None
    policy_overrides: dict[str, Any] | None = None
    synthetic_evaluation_scores: dict[str, float] | None = None


SELECTION_BIAS_WARNING = (
    "Multiple candidates were tested on the same train/validation window; "
    "reported ranks are subject to selection bias. Full FDR/Bonferroni deferred."
)


__all__ = [
    "ENGINE_VERSION",
    "CandidateStatus",
    "FactorCandidate",
    "GeneratorStrategy",
    "MiningJob",
    "MiningPlatformInject",
    "MiningRun",
    "MiningRunIndex",
    "MiningRunStatus",
    "MiningScore",
    "MINING_CANDIDATE_SCHEMA",
    "MINING_RUN_INDEX_SCHEMA",
    "MINING_SCORE_SCHEMA",
    "SELECTION_BIAS_WARNING",
]
