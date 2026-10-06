"""NormalizedBrokerEvent 构造。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from pydantic import Field

from app.services.research_data.contracts import _ContractModel

from .hash import compute_broker_event_id


class NormalizedBrokerEvent(_ContractModel):
    """归一化 Broker 事件（进入 ExecutionReport 前）。"""

    event_id: str
    broker_id: str
    broker_execution_id: str = ""
    client_order_id: str = ""
    broker_order_id: str = ""
    order_id: str = ""
    event_type: str = ""  # ACK | PARTIAL | FILL | CANCEL | REJECT | UNKNOWN
    quantity: float = 0.0
    price: float = 0.0
    filled_quantity: float = 0.0
    remaining_quantity: float = 0.0
    fee: float = 0.0
    currency: str = ""
    broker_timestamp: Optional[str] = None
    received_at: Optional[str] = None
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


def make_normalized_event(
    *,
    broker_id: str,
    broker_execution_id: str,
    event_type: str,
    client_order_id: str = "",
    broker_order_id: str = "",
    order_id: str = "",
    quantity: float = 0.0,
    price: float = 0.0,
    filled_quantity: float = 0.0,
    remaining_quantity: float = 0.0,
    fee: float = 0.0,
    currency: str = "",
    broker_timestamp: Optional[str] = None,
    message: str = "",
    payload: Mapping[str, Any] | None = None,
) -> NormalizedBrokerEvent:
    now = datetime.now(timezone.utc).isoformat()
    return NormalizedBrokerEvent(
        event_id=compute_broker_event_id(broker_id, broker_execution_id),
        broker_id=broker_id,
        broker_execution_id=broker_execution_id,
        client_order_id=client_order_id,
        broker_order_id=broker_order_id,
        order_id=order_id,
        event_type=event_type,
        quantity=float(quantity),
        price=float(price),
        filled_quantity=float(filled_quantity),
        remaining_quantity=float(remaining_quantity),
        fee=float(fee),
        currency=currency,
        broker_timestamp=broker_timestamp,
        received_at=now,
        message=message,
        payload=dict(payload or {}),
    )
