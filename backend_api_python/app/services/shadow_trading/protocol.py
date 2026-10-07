"""Phase 7B：Shadow Trading 契约（永不触达真实 Broker submit）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_shadow@1"

ShadowOrderStatus = Literal[
    "SUBMITTED",
    "ACCEPTED",
    "PARTIALLY_FILLED",
    "FILLED",
    "EXPIRED",
    "REJECTED",
    "CANCELLED",
]


class _ShadowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ShadowOrder(_ShadowModel):
    """Shadow 订单（含风控与版本锁定字段）。"""

    order_id: str
    strategy_id: str = ""
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    limit_price: Optional[float] = None
    status: ShadowOrderStatus = "SUBMITTED"
    filled_quantity: float = 0.0
    signal_time: str = ""
    decision_time: str = ""
    risk_approved: bool = False
    risk_decision: str = ""
    created_at: str = ""
    dataset_hash: str = ""
    model_version: str = ""
    strategy_version: str = ""
    client_order_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShadowExecution(_ShadowModel):
    """模拟成交明细。"""

    execution_id: str
    order_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    price: float
    fee: float = 0.0
    slippage_bps: float = 0.0
    executed_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShadowPosition(_ShadowModel):
    symbol: str
    quantity: float = 0.0
    avg_price: float = 0.0
    market_value: float = 0.0


class ShadowCompareFinding(_ShadowModel):
    symbol: str
    shadow_qty: float = 0.0
    live_qty: float = 0.0
    qty_delta: float = 0.0
    severity: str = "INFO"


class ShadowCompareReport(_ShadowModel):
    run_id: str
    account_id: str = ""
    findings: list[ShadowCompareFinding] = Field(default_factory=list)
    created_at: str = ""
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShadowSession(_ShadowModel):
    session_id: str
    account_id: str = ""
    environment: str = "SHADOW"
    dataset_hash: str = ""
    model_version: str = ""
    strategy_version: str = ""
    status: Literal["OPEN", "CLOSED"] = "OPEN"
    opened_at: str = ""
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)
