"""Alpaca Paper raw → OMS ExecutionReport 字段映射。"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.services.oms.hash import compute_fill_id
from app.services.oms.protocol import ExecutionReport, Fill, Order

from ...mapping import map_broker_status


def instrument_to_alpaca_symbol(instrument_key: str) -> str:
    """CNStock:xxx → 原样或取冒号后；US 股票多为 SYMBOL。"""
    key = str(instrument_key or "")
    if ":" in key:
        return key.split(":", 1)[1].upper()
    return key.upper()


def order_to_alpaca_payload(order: Order) -> dict[str, Any]:
    """OMS Order → Alpaca POST /v2/orders body。"""
    payload: dict[str, Any] = {
        "symbol": instrument_to_alpaca_symbol(order.instrument_key),
        "qty": str(order.quantity),
        "side": str(order.side).lower(),
        "type": str(order.order_type).lower(),
        "time_in_force": str(order.tif).lower()
        if str(order.tif).lower() in ("day", "gtc", "ioc", "fok")
        else "day",
        "client_order_id": order.client_order_id,
    }
    if str(order.order_type).upper() == "LIMIT" and order.limit_price is not None:
        payload["limit_price"] = str(order.limit_price)
    return payload


def alpaca_order_to_report(
    raw: Mapping[str, Any],
    *,
    order: Optional[Order] = None,
) -> ExecutionReport:
    """Alpaca order JSON → ExecutionReport。"""
    status = map_broker_status(str(raw.get("status") or ""), broker="alpaca")
    filled_qty = float(raw.get("filled_qty") or raw.get("filled_quantity") or 0)
    avg = float(raw.get("filled_avg_price") or raw.get("avg_fill_price") or 0 or 0)
    qty = float(raw.get("qty") or (order.quantity if order else 0) or 0)
    remaining = max(0.0, qty - filled_qty)
    broker_oid = str(raw.get("id") or raw.get("order_id") or "")
    client_id = str(
        raw.get("client_order_id")
        or (order.client_order_id if order else "")
    )
    fills: list[Fill] = []
    if status in ("FILL", "PARTIAL") and filled_qty > 0 and avg > 0:
        oid = order.order_id if order else str(raw.get("client_order_id") or "")
        fills.append(
            Fill(
                fill_id=compute_fill_id(
                    oid, quantity=filled_qty, price=avg, salt=broker_oid
                ),
                order_id=oid,
                instrument_key=(order.instrument_key if order else ""),
                side=(order.side if order else "BUY"),  # type: ignore[arg-type]
                quantity=filled_qty,
                price=avg,
                trading_date=(order.trading_date if order else ""),
                metadata={"broker_execution_id": broker_oid},
            )
        )
    return ExecutionReport(
        report_id=f"alpaca_{broker_oid[:16] or client_id[:16]}",
        order_id=(order.order_id if order else ""),
        client_order_id=client_id,
        broker_order_id=broker_oid,
        broker_event_id=broker_oid,
        status=status,
        filled_quantity=filled_qty,
        last_quantity=filled_qty,
        last_price=avg,
        avg_price=avg,
        remaining_quantity=remaining,
        fills=fills,
        message=str(raw.get("status") or ""),
        raw_reference={"alpaca_status": raw.get("status"), "id": broker_oid},
        broker_timestamp=str(raw.get("updated_at") or raw.get("submitted_at") or "")
        or None,
    )
