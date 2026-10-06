"""ExecutionReport / Fill → Order 派生字段。"""

from __future__ import annotations

from typing import Sequence

from .events import append_event
from .protocol import ExecutionReport, Fill, Order, OrderEvent
from .state_machine import StateMachineError


def apply_fill(order: Order, fill: Fill) -> Order:
    """累加 filled_quantity / avg_fill_price（事实在 Fill 列表）。"""
    prev_qty = float(order.filled_quantity)
    prev_avg = float(order.avg_fill_price)
    add = float(fill.quantity)
    px = float(fill.price)
    new_qty = prev_qty + add
    if new_qty <= 0:
        avg = 0.0
    elif prev_qty <= 0:
        avg = px
    else:
        avg = (prev_avg * prev_qty + px * add) / new_qty
    return order.model_copy(
        update={"filled_quantity": new_qty, "avg_fill_price": avg}
    )


def status_after_fill(order: Order) -> str:
    filled = float(order.filled_quantity)
    qty = float(order.quantity)
    if filled + 1e-12 >= qty:
        return "FILLED"
    if filled > 1e-12:
        return "PARTIALLY_FILLED"
    return str(order.status)


def apply_execution_report(
    order: Order, report: ExecutionReport
) -> tuple[Order, list[OrderEvent], list[Fill]]:
    """将 Paper/Broker 回报归约到 Order。"""
    events: list[OrderEvent] = []
    fills = list(report.fills or [])
    st = str(report.status or "").upper()
    cur = order

    if report.broker_order_id:
        cur = cur.model_copy(update={"broker_order_id": report.broker_order_id})

    if st in ("ACK", "ACKNOWLEDGED"):
        # 6E：UNKNOWN 经 get_order 恢复亦可进入 ACKNOWLEDGED
        if str(cur.status) in ("SUBMITTED", "REPLACED", "UNKNOWN"):
            cur, ev = append_event(
                cur,
                event_type="ACKNOWLEDGED",
                new_status="ACKNOWLEDGED",
                source="BROKER",
                message=report.message or "ack",
            )
            events.append(ev)
        return cur, events, fills

    if st in ("REJECT", "BROKER_REJECTED"):
        target = "BROKER_REJECTED"
        if str(cur.status) == "VALIDATED":
            target = "REJECTED"
        try:
            cur, ev = append_event(
                cur,
                event_type="BROKER_REJECTED",
                new_status=target,
                source="BROKER",
                message=report.message or "rejected",
            )
            events.append(ev)
        except StateMachineError:
            pass
        return cur, events, fills

    if st == "UNKNOWN":
        cur, ev = append_event(
            cur,
            event_type="UNKNOWN",
            new_status="UNKNOWN",
            source="BROKER",
            message=report.message or "timeout/unknown",
        )
        events.append(ev)
        return cur, events, fills

    if st == "CANCEL":
        if str(cur.status) != "CANCELLED":
            # 若尚未 CANCEL_PENDING，先进入再完成
            if str(cur.status) not in ("CANCEL_PENDING",):
                cur, ev = append_event(
                    cur,
                    event_type="CANCEL_PENDING",
                    new_status="CANCEL_PENDING",
                    source="OMS",
                    message="cancel ack path",
                )
                events.append(ev)
            cur, ev = append_event(
                cur,
                event_type="CANCELLED",
                new_status="CANCELLED",
                source="BROKER",
                message=report.message or "cancelled",
            )
            events.append(ev)
        return cur, events, fills

    # PARTIAL / FILL
    for i, fill in enumerate(fills):
        cur = apply_fill(cur, fill)
        target = status_after_fill(cur)
        if target != str(cur.status):
            cur, ev = append_event(
                cur,
                event_type="FILL" if target == "FILLED" else "PARTIAL_FILL",
                new_status=target,
                source="BROKER",
                message=f"fill {fill.quantity}@{fill.price}",
                payload={"fill_id": fill.fill_id},
                salt=f"fill|{fill.fill_id}|{i}",
            )
            events.append(ev)
        elif target == "PARTIALLY_FILLED":
            # 允许 PARTIALLY_FILLED → PARTIALLY_FILLED
            cur, ev = append_event(
                cur,
                event_type="PARTIAL_FILL",
                new_status="PARTIALLY_FILLED",
                source="BROKER",
                message=f"fill {fill.quantity}@{fill.price}",
                payload={"fill_id": fill.fill_id},
                salt=f"fill|{fill.fill_id}|{i}",
            )
            events.append(ev)

    if not fills and st in ("FILL", "FILLED", "PARTIAL", "PARTIALLY_FILLED"):
        # 无明细 fills 时用 report 汇总
        qty = float(report.last_quantity or report.filled_quantity or 0)
        px = float(report.last_price or report.avg_price or 0)
        if qty > 0 and px > 0:
            from .hash import compute_fill_id
            from datetime import datetime, timezone

            fill = Fill(
                fill_id=compute_fill_id(cur.order_id, quantity=qty, price=px, salt=st),
                order_id=cur.order_id,
                instrument_key=cur.instrument_key,
                side=cur.side,
                quantity=qty,
                price=px,
                fee=float(report.fee),
                trading_date=cur.trading_date,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            fills = [fill]
            cur = apply_fill(cur, fill)
            target = status_after_fill(cur)
            cur, ev = append_event(
                cur,
                event_type="FILL" if target == "FILLED" else "PARTIAL_FILL",
                new_status=target,
                source="BROKER",
                message=report.message or "fill",
                salt=f"report|{st}|{fill.fill_id}",
            )
            events.append(ev)

    return cur, events, fills
