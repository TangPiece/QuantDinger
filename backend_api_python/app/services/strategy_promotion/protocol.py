"""Phase 8D：Strategy Promotion Pipeline 契约（环境晋升，非 8B Research→REGISTERED）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_strategy_promotion@1"

PromotionEnvironment = Literal["REGISTERED", "SHADOW", "CONTROLLED_LIVE", "LIVE"]
PromotionRequestStatus = Literal[
    "PENDING",
    "APPROVED",
    "REJECTED",
    "EXECUTING",
    "COMPLETED",
    "INVALID",
]
PromotionRunStatus = Literal["IN_PROGRESS", "COMPLETED", "FAILED"]
PromotionStageName = Literal[
    "ELIGIBLE_CHECK",
    "REGISTRY_BIND",
    "GOV_SHADOW",
    "SHADOW_SESSION",
    "GOV_CONTROLLED_LIVE",
    "CL_SESSION",
    "GOV_LIVE",
    "LIVE_ELIGIBLE",
]


class _PromoModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PromotionApprovalRecord(_PromoModel):
    """人工审批钉扎（LIVE / CL 门槛）。"""

    kind: str
    operator: str = ""
    approved_at: str = ""
    token_hash: str = ""


class PromotionPolicyRules(_PromoModel):
    """版本化晋升规则；变更须 bump policy_content_hash。"""

    require_validation_passed: bool = True
    min_shadow_days: float = 0.0
    max_shadow_drawdown: float = 0.25
    max_shadow_drift: float = 0.15
    max_recon_errors: int = 0
    required_approval: bool = False
    min_controlled_days: float = 0.0
    max_live_drawdown: float = 0.2
    max_slippage: float = 0.05
    max_reject_rate: float = 0.1
    max_risk_breach: int = 0
    required_approval_count: int = 1
    require_l4_scale: bool = False


class PromotionPolicyRecord(_PromoModel):
    """PromotionPolicy SSOT（按 transition 版本化）。"""

    policy_id: str
    policy_version: str
    transition_key: str
    policy_content_hash: str
    rules: PromotionPolicyRules
    engine_version: str = ENGINE_VERSION
    description: str = ""


class PromotionRequest(_PromoModel):
    """晋升请求（钉死 validation_id + content_hash）。"""

    request_id: str
    pipeline_run_id: str
    idempotency_key: str
    strategy_code: str
    candidate_id: str
    validation_id: str
    strategy_version: str
    version_id: str = ""
    content_hash: str
    from_environment: PromotionEnvironment
    to_environment: PromotionEnvironment
    policy_id: str
    policy_version: str
    policy_content_hash: str
    status: PromotionRequestStatus = "PENDING"
    operator: str = ""
    approvals: list[PromotionApprovalRecord] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class PromotionStageRecord(_PromoModel):
    """管线阶段审计。"""

    stage: PromotionStageName
    status: Literal["OK", "SKIP", "FAIL"] = "OK"
    detail: dict[str, Any] = Field(default_factory=dict)
    at: str = ""


class PromotionRunRecord(_PromoModel):
    """不可变环境晋升 Run（8D SSOT，非 8B promotion 表）。"""

    pipeline_run_id: str
    request_id: str
    strategy_code: str
    from_environment: PromotionEnvironment
    to_environment: PromotionEnvironment
    policy_id: str
    policy_version: str
    policy_content_hash: str
    status: PromotionRunStatus = "IN_PROGRESS"
    stages: list[PromotionStageRecord] = Field(default_factory=list)
    session_id: str = ""
    governance_state: str = ""
    started_at: str = ""
    completed_at: str = ""
    operator: str = ""
    storage_uri: str = ""


class RollbackRecord(_PromoModel):
    """晋升回滚审计（PAUSE + 回切 previous stable version）。"""

    rollback_id: str
    strategy_code: str
    from_version: str
    to_version: str
    reason: str = ""
    operator: str = ""
    session_id: str = ""
    created_at: str = ""


__all__ = [
    "ENGINE_VERSION",
    "PromotionApprovalRecord",
    "PromotionEnvironment",
    "PromotionPolicyRecord",
    "PromotionPolicyRules",
    "PromotionRequest",
    "PromotionRequestStatus",
    "PromotionRunRecord",
    "PromotionRunStatus",
    "PromotionStageName",
    "PromotionStageRecord",
    "RollbackRecord",
]
