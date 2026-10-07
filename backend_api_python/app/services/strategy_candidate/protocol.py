"""Phase 8B：Strategy Candidate 契约（冻结 Research Lineage，非 Live 策略）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_strategy_candidate@1"

CandidateStatus = Literal[
    "DRAFT",
    "GENERATED",
    "EVALUATING",
    "READY_FOR_VALIDATION",
    "VALIDATED",
    "REJECTED",
    "EXPIRED",
]

CandidateSource = Literal["RESEARCH", "EXPERIMENT", "BACKTEST", "MANUAL"]

PromotionSourceType = Literal["EXPERIMENT", "BACKTEST", "MANUAL"]

PromotionToState = Literal["GENERATED", "VALIDATED", "REGISTERED"]

PromotionStatus = Literal["COMPLETED", "FAILED"]


class _CandModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StrategyCandidateRecord(_CandModel):
    """研究侧策略候选；VALIDATED 后 lineage 不可变，改 pin 须新 candidate。"""

    candidate_id: str
    strategy_code: str
    candidate_version: str
    experiment_id: str = ""
    backtest_hash: str = ""
    model_version: str = ""
    model_artifact_id: str = ""
    dataset_hash: str = ""
    snapshot_id: str = ""
    feature_version: str = ""
    processor_version: str = ""
    processor_hash: str = ""
    strategy_hash: str = ""
    strategy_definition_json: dict[str, Any] = Field(default_factory=dict)
    risk_policy_ref: str = ""
    execution_policy_ref: str = "NEXT_OPEN"
    evaluation_hash: str = ""
    cv_hash: str = ""
    content_hash: str = ""
    source: CandidateSource = "RESEARCH"
    status: CandidateStatus = "DRAFT"
    lineage_frozen_at: str = ""
    created_at: str = ""
    storage_uri: str = ""
    lineage_frozen: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromotionRecord(_CandModel):
    """晋升审计：研究证据 → Candidate →（可选）8A Registry version。"""

    promotion_id: str
    candidate_id: str
    source_type: PromotionSourceType = "EXPERIMENT"
    source_id: str = ""
    target_strategy_code: str = ""
    target_strategy_version: str = ""
    version_id: str = ""
    from_state: str = ""
    to_state: PromotionToState = "GENERATED"
    dataset_hash: str = ""
    model_version: str = ""
    operator: str = ""
    reason: str = ""
    status: PromotionStatus = "COMPLETED"
    created_at: str = ""


__all__ = [
    "ENGINE_VERSION",
    "CandidateSource",
    "CandidateStatus",
    "PromotionRecord",
    "PromotionSourceType",
    "PromotionStatus",
    "PromotionToState",
    "StrategyCandidateRecord",
]
