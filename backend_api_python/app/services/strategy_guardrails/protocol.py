"""Phase 8G：Strategy Guardrails 契约（Runtime 与 Lifecycle 分离，不改 Immutable Version）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_strategy_guardrails@1"

RuntimeStatus = Literal[
    "ACTIVE",
    "DEGRADED",
    "THROTTLED",
    "PAUSED",
    "STOPPING",
    "STOPPED",
    "ROLLBACK_PENDING",
    "ROLLING_BACK",
]
LifecyclePhase = Literal[
    "SHADOW",
    "CONTROLLED_LIVE",
    "LIVE",
    "RETIRED",
    "UNKNOWN",
]
ThrottleTier = Literal["NORMAL", "THROTTLED_75", "THROTTLED_50", "THROTTLED_25", "PAUSED"]
GuardrailActionType = Literal[
    "WARN",
    "THROTTLE",
    "PAUSE",
    "SAFETY_STOP",
    "STOP",
    "ROLLBACK",
    "RESUME",
    "REVIEW",
]
IncidentStatus = Literal[
    "DETECTED",
    "OPEN",
    "TRIAGED",
    "MITIGATING",
    "REVIEW_REQUIRED",
    "APPROVED",
    "REJECTED",
    "RESOLVED",
]
DecisionType = Literal[
    "CONTINUE",
    "THROTTLE",
    "PAUSE",
    "RESUME",
    "STOP",
    "ROLLBACK",
]
DecisionStatus = Literal["PENDING", "APPROVED", "REJECTED", "EXECUTED", "CANCELLED"]
GovernanceEventType = Literal[
    "STRATEGY_WARNED",
    "STRATEGY_THROTTLED",
    "STRATEGY_PAUSED",
    "STRATEGY_RESUMED",
    "STRATEGY_STOPPED",
    "STRATEGY_ROLLED_BACK",
    "GUARDRAIL_BREACH",
    "SAFETY_STOP_NEW_ORDERS",
    "INCIDENT_OPENED",
    "DECISION_SUBMITTED",
    "DECISION_EXECUTED",
]
MetricCategory = Literal[
    "PERFORMANCE",
    "RISK",
    "SIGNAL",
    "PORTFOLIO",
    "EXECUTION",
    "MARKET_DATA",
    "RECONCILIATION",
    "CAPACITY",
    "SYSTEM",
]


class _GrModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BreachSignal(_GrModel):
    """单条 Guardrail 评估输入（来自 8F Alert 或 Fake inject）。"""

    category: str
    severity: str
    metric: str = ""
    value: float = 0.0
    alert_id: str = ""
    message: str = ""


class ActionMatrixEntry(_GrModel):
    """Action Matrix 一行：category + severity → 建议动作。"""

    category: str
    severity: str
    action: GuardrailActionType
    metric: str = ""
    description: str = ""


class AutoActionPolicyRecord(_GrModel):
    """自动动作白名单（默认仅 WARN/THROTTLE/PAUSE）。"""

    policy_id: str
    policy_version: str
    policy_content_hash: str = ""
    auto_allowed: list[str] = Field(default_factory=lambda: ["WARN", "THROTTLE", "PAUSE"])
    auto_forbidden: list[str] = Field(
        default_factory=lambda: ["STOP", "ROLLBACK", "PROMOTE", "RETIRE", "DEMOTE"]
    )
    auto_resume: bool = False
    engine_version: str = ENGINE_VERSION
    description: str = ""


class GuardrailPolicyRecord(_GrModel):
    """GuardrailPolicy SSOT（含 auto_execute 开关）。"""

    policy_id: str
    policy_version: str
    policy_content_hash: str
    auto_execute: bool = True
    auto_action_policy_id: str = ""
    auto_action_policy_version: str = ""
    action_matrix: list[ActionMatrixEntry] = Field(default_factory=list)
    engine_version: str = ENGINE_VERSION
    description: str = ""


class StrategyRuntimeState(_GrModel):
    """Runtime 状态（与 8D/7E Lifecycle 分表/分字段）。"""

    strategy_code: str
    runtime_status: RuntimeStatus = "ACTIVE"
    lifecycle_phase: LifecyclePhase = "UNKNOWN"
    throttle_tier: ThrottleTier = "NORMAL"
    throttle_multiplier: float = 1.0
    policy_id: str = ""
    policy_version: str = ""
    policy_content_hash: str = ""
    last_incident_id: str = ""
    recovery_check_passed: bool = False
    last_evaluated_at: str = ""
    session_id: str = ""
    engine_version: str = ENGINE_VERSION
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovernanceIncident(_GrModel):
    """治理事件 FSM（Performance CRITICAL 等 → REVIEW_REQUIRED）。"""

    incident_id: str
    strategy_code: str
    status: IncidentStatus = "DETECTED"
    severity: str = "CRITICAL"
    category: str = "SYSTEM"
    recommended_action: GuardrailActionType = "REVIEW"
    alert_id: str = ""
    message: str = ""
    requires_decision: bool = False
    opened_at: str = ""
    resolved_at: str = ""
    session_id: str = ""
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovernanceDecision(_GrModel):
    """人工 Governance 决策（STOP/ROLLBACK/RESUME 等）。"""

    decision_id: str
    strategy_code: str
    incident_id: str = ""
    decision_type: DecisionType
    status: DecisionStatus = "PENDING"
    operator: str = ""
    reason: str = ""
    to_version: str = ""
    submitted_at: str = ""
    approved_at: str = ""
    executed_at: str = ""
    session_id: str = ""
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovernanceEvent(_GrModel):
    """8G 审计流（与 8F strategy_governance_event 并存）。"""

    event_id: str
    strategy_code: str
    event_type: GovernanceEventType
    runtime_status: RuntimeStatus = "ACTIVE"
    lifecycle_phase: LifecyclePhase = "UNKNOWN"
    severity: str = "INFO"
    category: str = "SYSTEM"
    incident_id: str = ""
    decision_id: str = ""
    message: str = ""
    created_at: str = ""
    session_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuardrailRollbackRecord(_GrModel):
    """完整 lineage 回滚记录（8D RollbackRecord + model/dataset 字段）。"""

    rollback_id: str
    strategy_code: str
    from_version: str
    to_version: str
    from_model_version: str = ""
    to_model_version: str = ""
    from_dataset_hash: str = ""
    to_dataset_hash: str = ""
    decision_id: str = ""
    reason: str = ""
    operator: str = ""
    session_id: str = ""
    created_at: str = ""
    storage_uri: str = ""
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuardrailEvaluationResult(_GrModel):
    """单次 evaluate_from_monitoring 输出。"""

    strategy_code: str
    runtime: StrategyRuntimeState
    actions_applied: list[str] = Field(default_factory=list)
    incidents: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    skipped_forbidden: list[str] = Field(default_factory=list)
    evaluated_at: str = ""
    session_id: str = ""


__all__ = [
    "ENGINE_VERSION",
    "ActionMatrixEntry",
    "AutoActionPolicyRecord",
    "BreachSignal",
    "DecisionStatus",
    "DecisionType",
    "GovernanceDecision",
    "GovernanceEvent",
    "GovernanceEventType",
    "GovernanceIncident",
    "GuardrailActionType",
    "GuardrailEvaluationResult",
    "GuardrailPolicyRecord",
    "GuardrailRollbackRecord",
    "IncidentStatus",
    "LifecyclePhase",
    "RuntimeStatus",
    "StrategyRuntimeState",
    "ThrottleTier",
]
