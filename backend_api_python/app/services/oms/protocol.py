"""Phase 6D：OMS Domain（Order 状态机；停在 Paper Broker）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from app.services.research_data.contracts import (
    OmsFillSummary,
    OmsOrderEventRecord,
    OmsOrderSummary,
    OmsOutboxRecord,
    OrderIntent,
    _ContractModel,
)

ENGINE_VERSION = "qd_oms@1"

OrderStatus = Literal[
    "CREATED",
    "VALIDATED",
    "SUBMITTED",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCEL_PENDING",
    "CANCELLED",
    "REPLACE_PENDING",
    "REPLACED",
    "REJECTED",
    "BROKER_REJECTED",
    "UNKNOWN",
]

OrderType = Literal["MARKET", "LIMIT"]
TimeInForce = Literal["DAY", "GTC", "IOC", "FOK"]
OrderSide = Literal["BUY", "SELL"]
OutboxStatus = Literal["PENDING", "SENT", "FAILED"]


class Order(_ContractModel):
    """可执行订单（由 OrderIntent 映射；状态由 OrderEvent 归约）。"""

    order_id: str
    client_order_id: str
    broker_order_id: str = ""
    account_id: str = ""
    portfolio_id: str = ""
    risk_run_id: str = ""
    policy_hash: str = ""
    instrument_key: str = ""
    side: OrderSide = "BUY"
    order_type: OrderType = "MARKET"
    tif: TimeInForce = "DAY"
    quantity: float = 0.0
    limit_price: Optional[float] = None
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    status: OrderStatus = "CREATED"
    version: int = 1
    idempotency_key: str = ""
    trading_date: str = ""
    engine_version: str = ENGINE_VERSION
    storage_uri: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderVersion(_ContractModel):
    """改单产生的版本快照。"""

    order_id: str
    version: int
    quantity: float = 0.0
    limit_price: Optional[float] = None
    status: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderEvent(_ContractModel):
    """订单生命周期事件（状态机权威输入）。"""

    event_id: str
    order_id: str
    event_type: str
    previous_status: str = ""
    new_status: str = ""
    source: str = "OMS"
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class Fill(_ContractModel):
    """成交事实（filled_qty/avg_price 由此派生）。"""

    fill_id: str
    order_id: str
    instrument_key: str = ""
    side: OrderSide = "BUY"
    quantity: float = 0.0
    price: float = 0.0
    fee: float = 0.0
    trading_date: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionReport(_ContractModel):
    """Broker（含 Paper）回报；6E 扩展字段向后兼容。"""

    report_id: str = ""
    order_id: str = ""
    client_order_id: str = ""
    broker_order_id: str = ""
    broker_event_id: str = ""
    status: str = ""  # ACK / PARTIAL / FILL / REJECT / CANCEL / UNKNOWN
    filled_quantity: float = 0.0
    last_quantity: float = 0.0
    last_price: float = 0.0
    avg_price: float = 0.0
    remaining_quantity: float = 0.0
    fee: float = 0.0
    currency: str = ""
    broker_timestamp: Optional[str] = None
    received_at: Optional[str] = None
    message: str = ""
    fills: list[Fill] = Field(default_factory=list)
    # 小摘要；完整 raw 在 R2 broker-events
    raw_reference: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CancelRequest(_ContractModel):
    """撤单请求。"""

    request_id: str
    order_id: str
    status: str = "PENDING"
    reason: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplaceRequest(_ContractModel):
    """改单请求（走 Version）。"""

    request_id: str
    order_id: str
    status: str = "PENDING"
    quantity: Optional[float] = None
    limit_price: Optional[float] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutboxRecord(_ContractModel):
    """与 Order 同事务语义入队的投递记录。"""

    outbox_id: str
    aggregate_type: str = "ORDER"
    aggregate_id: str = ""
    event_type: str = ""
    status: OutboxStatus = "PENDING"
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    sent_at: Optional[str] = None


class SubmitResult(_ContractModel):
    """submit_intents 结果。"""

    orders: list[Order] = Field(default_factory=list)
    fills: list[Fill] = Field(default_factory=list)
    events: list[OrderEvent] = Field(default_factory=list)
    outbox_ids: list[str] = Field(default_factory=list)
    position_events: list[Any] = Field(default_factory=list)
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ENGINE_VERSION",
    "CancelRequest",
    "ExecutionReport",
    "Fill",
    "OmsFillSummary",
    "OmsOrderEventRecord",
    "OmsOrderSummary",
    "OmsOutboxRecord",
    "Order",
    "OrderEvent",
    "OrderIntent",
    "OrderStatus",
    "OrderType",
    "OrderVersion",
    "OutboxRecord",
    "ReplaceRequest",
    "SubmitResult",
    "TimeInForce",
]
