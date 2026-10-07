"""Phase 7C/7D：Controlled Live 契约（LIMIT real submit + 7D 生产 session 锁）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_controlled_live@2"

RuntimePhase = Literal[
    "INIT",
    "PRE_TICK",
    "INFER",
    "SUBMIT",
    "RECON",
    "POST_TICK",
    "HALTED",
    "CLOSED",
]

SessionStatus = Literal["OPEN", "CLOSED", "SAFETY_HOLD", "HALTED"]

ControlledOrderStatus = Literal[
    "PENDING_SUBMIT",
    "SUBMITTED",
    "ACCEPTED",
    "PARTIALLY_FILLED",
    "FILLED",
    "REJECTED",
    "EXPIRED",
    "UNKNOWN",
    "RECOVERED",
]

ApprovalStatus = Literal["PENDING", "APPROVED", "REVOKED"]


class _ControlledModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ControlledLiveConfig(_ControlledModel):
    """爆炸半径配置（来自 env，不写死到业务常量）。"""

    max_orders: int = 1
    max_quantity: float = 10.0
    max_notional: float = 5000.0
    allowed_symbols: tuple[str, ...] = ("AAPL",)
    allowed_sides: tuple[str, ...] = ("BUY",)
    allowed_order_types: tuple[str, ...] = ("LIMIT",)


class RiskBudget(_ControlledModel):
    """Session / 日级风险预算（金额来自 env，非硬编码）。"""

    max_orders: int = 1
    max_notional_session: float = 5000.0
    max_turnover_session: float = 10000.0
    max_daily_loss: float = 500.0
    max_consecutive_rejects: int = 3
    max_consecutive_errors: int = 3
    session_notional_used: float = 0.0
    session_turnover_used: float = 0.0
    consecutive_rejects: int = 0
    consecutive_errors: int = 0


class ControlledSession(_ControlledModel):
    """Controlled Live 会话（锁定 hash/版本）；7D 亦称 TradingSession。"""

    session_id: str
    account_id: str = ""
    environment: str = "LIVE_CONTROLLED"
    approved_strategy_id: str = ""
    dataset_hash: str = ""
    model_version: str = ""
    strategy_version: str = ""
    feature_version: str = ""
    processor_version: str = ""
    snapshot_id: str = ""
    status: SessionStatus = "OPEN"
    stop_reason: str = ""
    order_count: int = 0
    opened_at: str = ""
    heartbeat_at: str = ""
    runtime_phase: RuntimePhase = "INIT"
    engine_version: str = ENGINE_VERSION
    config: ControlledLiveConfig = Field(default_factory=ControlledLiveConfig)
    risk_budget: RiskBudget = Field(default_factory=RiskBudget)
    metadata: dict[str, Any] = Field(default_factory=dict)


# 7D 文档/编排层别名
TradingSession = ControlledSession


class OperatorApproval(_ControlledModel):
    """Operator 审批审计（不含密钥）。"""

    approval_id: str
    session_id: str = ""
    operator_actor: str = ""
    approval_token_hash: str = ""
    scope: str = "SINGLE_ORDER"
    status: ApprovalStatus = "APPROVED"
    approved_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ControlledOrder(_ControlledModel):
    """真实穿透订单（含 lineage metadata）。"""

    order_id: str
    session_id: str = ""
    client_order_id: str = ""
    broker_order_id: str = ""
    symbol: str = ""
    side: Literal["BUY", "SELL"] = "BUY"
    order_type: Literal["LIMIT"] = "LIMIT"
    quantity: float = 0.0
    limit_price: Optional[float] = None
    status: ControlledOrderStatus = "PENDING_SUBMIT"
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    lineage: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShadowVsRealFinding(_ControlledModel):
    """Shadow 与 Real 成交 Δ。"""

    symbol: str
    shadow_qty: float = 0.0
    real_qty: float = 0.0
    qty_delta: float = 0.0
    shadow_avg_price: float = 0.0
    real_avg_price: float = 0.0
    slippage_bps: float = 0.0
    fee_delta: float = 0.0
    latency_ms: float = 0.0
    severity: str = "INFO"


class ShadowVsRealReport(_ControlledModel):
    run_id: str
    order_id: str = ""
    account_id: str = ""
    findings: list[ShadowVsRealFinding] = Field(default_factory=list)
    created_at: str = ""
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)
