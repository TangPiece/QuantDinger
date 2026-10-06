"""Cancel 请求：Order → CANCEL_PENDING → Paper cancel → CANCELLED。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .events import append_event
from .hash import compute_request_id
from .paper_broker import PaperBroker
from .protocol import CancelRequest, Order, OrderEvent
from .reducer import apply_execution_report
from .state_machine import StateMachineError, is_terminal


def build_cancel_request(order_id: str, *, reason: str = "") -> CancelRequest:
    now = datetime.now(timezone.utc).isoformat()
    return CancelRequest(
        request_id=compute_request_id(order_id, "cancel", salt=now),
        order_id=order_id,
        status="PENDING",
        reason=reason,
        created_at=now,
    )


def apply_cancel(
    order: Order,
    *,
    reason: str = "",
    paper_broker: PaperBroker | None = None,
) -> tuple[Order, list[OrderEvent], CancelRequest]:
    """执行撤单；终态订单拒绝。"""
    if is_terminal(order.status):
        raise StateMachineError(f"cannot cancel terminal order {order.status}")
    events: list[OrderEvent] = []
    cur = order
    if str(cur.status) != "CANCEL_PENDING":
        cur, ev = append_event(
            cur,
            event_type="CANCEL_PENDING",
            new_status="CANCEL_PENDING",
            source="OMS",
            message=reason or "cancel requested",
        )
        events.append(ev)

    req = build_cancel_request(cur.order_id, reason=reason)
    broker = paper_broker or PaperBroker()
    report = broker.cancel(cur, reason=reason)
    cur, more, _ = apply_execution_report(cur, report)
    events.extend(more)
    req = req.model_copy(update={"status": "DONE"})
    return cur, events, req
