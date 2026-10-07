"""Phase 7E：Trading Governance 契约（Gradual Scale / 多策略多账户治理）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_governance@1"

StrategyLifecycleState = Literal[
    "DRAFT",
    "VALIDATING",
    "SHADOW",
    "CONTROLLED_LIVE",
    "LIVE",
    "PAUSED",
    "STOPPED",
    "RETIRED",
]

ScaleLevel = Literal[
    "L0_SHADOW",
    "L1_CONTROLLED",
    "L2_SMALL",
    "L3_MEDIUM",
    "L4_PRODUCTION",
]

ApprovalKind = Literal[
    "SCALE_UP",
    "LIVE_ENV",
    "STRATEGY_GO_LIVE",
]

ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED", "REVOKED"]


class _GovModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StrategyVersionPin(_GovModel):
    """策略不可变版本钉扎（LIVE 中禁止原地修改）。"""

    strategy_id: str
    strategy_version: str
    model_version: str = ""
    dataset_hash: str = ""
    feature_version: str = ""
    content_hash: str = ""
    is_live: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyLifecycleRecord(_GovModel):
    strategy_id: str
    state: StrategyLifecycleState = "DRAFT"
    active_version: str = ""
    previous_stable_version: str = ""
    scale_level: ScaleLevel = "L0_SHADOW"
    updated_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapitalAllocation(_GovModel):
    account_id: str
    strategy_id: str
    allocated_notional: float = 0.0
    reserve_notional: float = 0.0
    used_notional: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskBudgetLayer(_GovModel):
    """单层风险预算（Account / Portfolio / Strategy / Order）。"""

    scope: Literal["ACCOUNT", "PORTFOLIO", "STRATEGY", "ORDER"]
    scope_id: str
    max_exposure: float
    max_notional: float = 0.0
    max_orders: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskBudgetLayers(_GovModel):
    account_id: str
    portfolio_id: str = ""
    strategy_id: str = ""
    layers: tuple[RiskBudgetLayer, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapacityLimit(_GovModel):
    strategy_id: str
    max_notional: float = 0.0
    max_order_size: float = 0.0
    max_participation_rate: float = 0.0
    max_daily_turnover: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EffectiveCaps(_GovModel):
    """Session 打开时快照：scale ∩ capital ∩ capacity ∩ env floor。"""

    account_id: str
    strategy_id: str
    scale_level: ScaleLevel = "L0_SHADOW"
    max_notional_per_order: float = 0.0
    max_notional_session: float = 0.0
    max_orders: int = 0
    max_order_size: float = 0.0
    environment: str = "LIVE_CONTROLLED"
    live_env_authorized: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScaleState(_GovModel):
    strategy_id: str
    account_id: str = ""
    current_level: ScaleLevel = "L0_SHADOW"
    pending_level: Optional[ScaleLevel] = None
    live_env_approved: bool = False
    updated_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScaleCriteriaReport(_GovModel):
    """升档建议报告（多指标）；不足时仍须人工 approve，禁止自动升档。"""

    strategy_id: str
    from_level: ScaleLevel
    to_level: ScaleLevel
    metrics: dict[str, Any] = Field(default_factory=dict)
    criteria_met: bool = False
    recommendation: str = "MANUAL_APPROVAL_REQUIRED"
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovernanceApproval(_GovModel):
    approval_id: str
    kind: ApprovalKind
    strategy_id: str = ""
    account_id: str = ""
    operator_actor: str = ""
    approval_token_hash: str = ""
    status: ApprovalStatus = "PENDING"
    from_scale: str = ""
    to_scale: str = ""
    approved_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AccountRegistryEntry(_GovModel):
    account_id: str
    label: str = ""
    environment: str = "LIVE_CONTROLLED"
    status: str = "ACTIVE"
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyAccountBind(_GovModel):
    strategy_id: str
    account_id: str
    portfolio_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyTarget(_GovModel):
    strategy_id: str
    instrument_key: str
    side: Literal["BUY", "SELL"]
    quantity: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioTarget(_GovModel):
    account_id: str
    instrument_key: str
    net_side: Literal["BUY", "SELL", "FLAT"]
    net_quantity: float = 0.0
    legs: tuple[StrategyTarget, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class AttributionRow(_GovModel):
    account_id: str
    strategy_id: str
    instrument_key: str
    quantity: float = 0.0
    notional: float = 0.0
    unrealized_pnl: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderRiskContext(_GovModel):
    """下单前四层预算校验上下文。"""

    account_id: str
    strategy_id: str
    portfolio_id: str = ""
    notional: float = 0.0
    quantity: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
