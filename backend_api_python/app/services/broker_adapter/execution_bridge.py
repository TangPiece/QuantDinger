"""NormalizedBrokerEvent → oms.ExecutionReport + Fill。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.services.oms.hash import compute_fill_id
from app.services.oms.protocol import ExecutionReport, Fill, Order

from .events import NormalizedBrokerEvent
from .mapping import map_broker_status


def event_to_execution_report(
    event: NormalizedBrokerEvent,
    *,
    order: Optional[Order] = None,
    broker: str = "simulated",
) -> ExecutionReport:
    """将归一化事件转为 OMS ExecutionReport。"""
    status = map_broker_status(event.event_type, broker=broker)
    # 若 event_type 已是 OMS status 字面量则直通
    if event.event_type.upper() in (
        "ACK",
        "PARTIAL",
        "FILL",
        "CANCEL",
        "REJECT",
        "UNKNOWN",
    ):
        status = event.event_type.upper()

    fills: list[Fill] = []
    if status in ("PARTIAL", "FILL") and float(event.quantity) > 0:
        oid = event.order_id or (order.order_id if order else "")
        fills.append(
            Fill(
                fill_id=compute_fill_id(
                    oid or event.client_order_id,
                    quantity=float(event.quantity),
                    price=float(event.price),
                    salt=event.broker_execution_id or event.event_id,
                ),
                order_id=oid,
                instrument_key=(order.instrument_key if order else ""),
                side=(order.side if order else "BUY"),  # type: ignore[arg-type]
                quantity=float(event.quantity),
                price=float(event.price),
                fee=float(event.fee),
                trading_date=(order.trading_date if order else ""),
                created_at=event.received_at
                or datetime.now(timezone.utc).isoformat(),
                metadata={"broker_execution_id": event.broker_execution_id},
            )
        )

    return ExecutionReport(
        report_id=event.event_id,
        order_id=event.order_id or (order.order_id if order else ""),
        client_order_id=event.client_order_id
        or (order.client_order_id if order else ""),
        broker_order_id=event.broker_order_id,
        broker_event_id=event.broker_execution_id or event.event_id,
        status=status,
        filled_quantity=float(event.filled_quantity or event.quantity),
        last_quantity=float(event.quantity),
        last_price=float(event.price),
        avg_price=float(event.price),
        remaining_quantity=float(event.remaining_quantity),
        fee=float(event.fee),
        currency=event.currency,
        broker_timestamp=event.broker_timestamp,
        received_at=event.received_at,
        message=event.message,
        fills=fills,
        raw_reference={
            "broker_id": event.broker_id,
            "broker_execution_id": event.broker_execution_id,
            "event_id": event.event_id,
        },
        metadata=dict(event.payload or {}),
    )


def order_view_to_execution_report(
    *,
    order: Order,
    broker_status: str,
    broker_order_id: str = "",
    filled_quantity: float = 0.0,
    avg_price: float = 0.0,
    message: str = "",
    broker: str = "simulated",
) -> ExecutionReport:
    """查询恢复：BrokerOrderView 摘要 → ExecutionReport。"""
    status = map_broker_status(broker_status, broker=broker)
    return ExecutionReport(
        report_id=f"query_{order.order_id[:12]}",
        order_id=order.order_id,
        client_order_id=order.client_order_id,
        broker_order_id=broker_order_id or order.broker_order_id,
        status=status,
        filled_quantity=float(filled_quantity),
        avg_price=float(avg_price),
        remaining_quantity=max(0.0, float(order.quantity) - float(filled_quantity)),
        message=message or "recovered from get_order",
        received_at=datetime.now(timezone.utc).isoformat(),
    )
