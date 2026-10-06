"""Phase 6C：Risk Engine Domain（停在 OrderIntent；无 OMS/Broker）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import Field

from app.services.research_data.contracts import (
    OrderIntent,
    RiskDecisionEventRecord,
    RiskPolicySummary,
    RiskRunSummary,
    Signal,
    TargetPosition,
    _ContractModel,
)
from app.services.portfolio_service.protocol import (
    Account,
    ApplyTargetsResult,
    Exposure,
    Portfolio,
    Position,
    PositionDelta,
)

ENGINE_VERSION = "qd_risk_engine@1"

RiskVerdict = Literal["ALLOW", "ALLOW_REDUCE", "MODIFY", "REJECT", "ERROR"]
RiskSeverity = Literal["P0", "P1", "P2"]


class RiskPolicy(_ContractModel):
    """版本化风控策略（可挂 Bundle）。"""

    policy_code: str = "default"
    policy_version: str = "1"
    policy_hash: str = ""
    max_single_position_weight: float = 0.10
    max_gross_exposure: float = 1.0
    max_turnover: float = 0.30
    max_position_delta_weight: float = 0.05
    data_freshness_seconds: float = 86400.0
    signal_ttl_seconds: float = 172800.0
    require_universe: bool = False
    universe_membership: list[str] = Field(default_factory=list)
    short_allowed: bool = False
    # True：超限时 MODIFY 裁剪；False：超限 REJECT
    clip_on_limit: bool = True
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskContext(_ContractModel):
    """风控求值上下文。"""

    account: Optional[Account] = None
    portfolio: Optional[Portfolio] = None
    positions: dict[str, Position] = Field(default_factory=dict)
    targets: list[TargetPosition] = Field(default_factory=list)
    deltas: list[PositionDelta] = Field(default_factory=list)
    exposure: Exposure = Field(default_factory=Exposure)
    prices: dict[str, float] = Field(default_factory=dict)
    trading_status: dict[str, dict[str, Any]] = Field(default_factory=dict)
    signals: list[Signal] = Field(default_factory=list)
    knowledge_time: Optional[datetime] = None
    market_data_as_of: Optional[datetime] = None
    trading_date: str = ""
    account_id: str = ""
    portfolio_id: str = ""
    apply_id: str = ""
    runtime_id: str = ""
    bundle_hash: str = ""
    policy: RiskPolicy = Field(default_factory=RiskPolicy)
    equity: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskResult(_ContractModel):
    """单条规则结果。"""

    rule_code: str
    decision: RiskVerdict = "ALLOW"
    severity: RiskSeverity = "P0"
    message: str = ""
    instrument_key: str = ""
    original_value: float = 0.0
    limit_value: float = 0.0
    # 可选：建议裁剪后的目标权重 / 数量
    adjusted_target_weight: Optional[float] = None
    adjusted_target_quantity: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskViolation(_ContractModel):
    """违规摘要（UI / 审计）。"""

    rule_code: str
    instrument_key: str = ""
    message: str = ""
    severity: RiskSeverity = "P0"
    original_value: float = 0.0
    limit_value: float = 0.0


class RiskDecision(_ContractModel):
    """聚合决策。"""

    verdict: RiskVerdict = "ALLOW"
    results: list[RiskResult] = Field(default_factory=list)
    violations: list[RiskViolation] = Field(default_factory=list)
    adjusted_deltas: list[PositionDelta] = Field(default_factory=list)
    message: str = ""


class RiskSnapshot(_ContractModel):
    """单次 evaluate 快照。"""

    risk_run_id: str
    account_id: str = ""
    portfolio_id: str = ""
    apply_id: str = ""
    runtime_id: str = ""
    bundle_hash: str = ""
    policy_hash: str = ""
    trading_date: str = ""
    timestamp: Optional[str] = None
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    max_position: float = 0.0
    turnover: float = 0.0
    available_cash: float = 0.0
    risk_status: RiskVerdict = "ALLOW"
    engine_version: str = ENGINE_VERSION
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskDecisionEvent(_ContractModel):
    """决策事件（ALLOW/MODIFY/REJECT 落库）。"""

    event_id: str
    risk_run_id: str
    rule_code: str = ""
    decision: RiskVerdict | str = "ALLOW"
    severity: RiskSeverity = "P0"
    instrument_key: str = ""
    message: str = ""
    original_value: float = 0.0
    limit_value: float = 0.0
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class RiskEvaluateResult(_ContractModel):
    """evaluate 出口：OrderIntent + 审计。"""

    risk_run_id: str
    idempotency_key: str = ""
    policy_hash: str = ""
    verdict: RiskVerdict = "ALLOW"
    reused: bool = False
    status: Literal["OK", "SKIPPED_IDEMPOTENT", "FAILED"] = "OK"
    decision: Optional[RiskDecision] = None
    adjusted_deltas: list[PositionDelta] = Field(default_factory=list)
    order_intents: list[OrderIntent] = Field(default_factory=list)
    violations: list[RiskViolation] = Field(default_factory=list)
    snapshot: Optional[RiskSnapshot] = None
    events: list[RiskDecisionEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ENGINE_VERSION",
    "Account",
    "ApplyTargetsResult",
    "Exposure",
    "OrderIntent",
    "Position",
    "PositionDelta",
    "RiskContext",
    "RiskDecision",
    "RiskDecisionEvent",
    "RiskDecisionEventRecord",
    "RiskEvaluateResult",
    "RiskPolicy",
    "RiskPolicySummary",
    "RiskResult",
    "RiskRunSummary",
    "RiskSnapshot",
    "RiskVerdict",
    "RiskViolation",
    "Signal",
    "TargetPosition",
]
