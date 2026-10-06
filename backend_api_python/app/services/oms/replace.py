"""Replace 请求：走 OrderVersion；禁止直接乱改已 SUBMITTED 字段。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .events import append_event
from .hash import compute_request_id
from .paper_broker import PaperBroker
from .protocol import Order, OrderEvent, OrderVersion, ReplaceRequest
from .state_machine import StateMachineError, is_terminal
from .validation import ValidationError, validate_replace


def build_replace_request(
    order_id: str,
    *,
    quantity: Optional[float] = None,
    limit_price: Optional[float] = None,
) -> ReplaceRequest:
    now = datetime.now(timezone.utc).isoformat()
    return ReplaceRequest(
        request_id=compute_request_id(order_id, "replace", salt=now),
        order_id=order_id,
        status="PENDING",
        quantity=quantity,
        limit_price=limit_price,
        created_at=now,
    )


def apply_replace(
    order: Order,
    *,
    quantity: Optional[float] = None,
    limit_price: Optional[float] = None,
    paper_broker: PaperBroker | None = None,
) -> tuple[Order, list[OrderEvent], OrderVersion, ReplaceRequest]:
    """改单：REPLACE_PENDING → 新 Version → REPLACED → ACK。"""
    if is_terminal(order.status):
        raise StateMachineError(f"cannot replace terminal order {order.status}")
    if quantity is None and limit_price is None:
        raise ValidationError("replace requires quantity or limit_price")
    validate_replace(quantity=quantity, limit_price=limit_price)

    # 已成交数量不可被改小到低于 filled
    new_qty = float(quantity) if quantity is not None else float(order.quantity)
    if new_qty + 1e-12 < float(order.filled_quantity):
        raise ValidationError("replace quantity < filled_quantity")

    events: list[OrderEvent] = []
    cur = order
    if str(cur.status) not in ("REPLACE_PENDING",):
        cur, ev = append_event(
            cur,
            event_type="REPLACE_PENDING",
            new_status="REPLACE_PENDING",
            source="OMS",
            message="replace requested",
            payload={"quantity": quantity, "limit_price": limit_price},
        )
        events.append(ev)

    now = datetime.now(timezone.utc).isoformat()
    new_version = int(cur.version) + 1
    updates: dict = {"version": new_version, "updated_at": now}
    if quantity is not None:
        updates["quantity"] = float(quantity)
    if limit_price is not None:
        updates["limit_price"] = float(limit_price)
        updates["order_type"] = "LIMIT"

    cur = cur.model_copy(update=updates)
    ver = OrderVersion(
        order_id=cur.order_id,
        version=new_version,
        quantity=float(cur.quantity),
        limit_price=cur.limit_price,
        status="REPLACED",
        created_at=now,
        metadata={"previous_version": order.version},
    )
    cur, ev = append_event(
        cur,
        event_type="REPLACED",
        new_status="REPLACED",
        source="OMS",
        message=f"replaced to v{new_version}",
        payload={"version": new_version},
        salt=f"replaced|{new_version}",
    )
    events.append(ev)

    broker = paper_broker or PaperBroker()
    report = broker.replace(cur, quantity=quantity, limit_price=limit_price)
    # Paper replace ACK → ACKNOWLEDGED
    if str(report.status).upper() in ("ACK", "ACKNOWLEDGED"):
        cur, ev = append_event(
            cur,
            event_type="ACKNOWLEDGED",
            new_status="ACKNOWLEDGED",
            source="BROKER",
            message=report.message or "replace ack",
            salt=f"replace_ack|{new_version}",
        )
        events.append(ev)

    req = build_replace_request(
        cur.order_id, quantity=quantity, limit_price=limit_price
    )
    req = req.model_copy(update={"status": "DONE"})
    return cur, events, ver, req
