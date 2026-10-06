"""append OrderEvent + 状态迁移。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .hash import compute_event_id
from .protocol import Order, OrderEvent
from .state_machine import assert_transition


def append_event(
    order: Order,
    *,
    event_type: str,
    new_status: str,
    source: str = "OMS",
    message: str = "",
    payload: Mapping[str, Any] | None = None,
    salt: str = "",
) -> tuple[Order, OrderEvent]:
    """校验迁移并返回更新后的 Order + Event。"""
    prev = str(order.status)
    assert_transition(prev, new_status)
    now = datetime.now(timezone.utc).isoformat()
    ev = OrderEvent(
        event_id=compute_event_id(
            order.order_id, event_type, salt=salt or f"{prev}->{new_status}|{now}"
        ),
        order_id=order.order_id,
        event_type=event_type,
        previous_status=prev,
        new_status=new_status,
        source=source,
        message=message,
        payload=dict(payload or {}),
        created_at=now,
    )
    updated = order.model_copy(
        update={"status": new_status, "updated_at": now}  # type: ignore[arg-type]
    )
    return updated, ev
