"""Phase 7C：UNKNOWN/timeout 仅 query by_client_order_id，禁止二次 submit。"""

from __future__ import annotations

from typing import Any, Callable, Protocol

from .protocol import ControlledOrder


class ClientOrderQueryPort(Protocol):
    """Broker 侧按 client_order_id 查询。"""

    def get_order_by_client_id(self, client_order_id: str) -> dict[str, Any]: ...


def recover_unknown_order(
    *,
    order: ControlledOrder,
    query_port: ClientOrderQueryPort,
    map_broker_status: Callable[[dict[str, Any]], str] | None = None,
) -> ControlledOrder:
    """网络 UNKNOWN 后只查询；永不 POST。"""
    raw = query_port.get_order_by_client_id(order.client_order_id)
    mapper = map_broker_status or _default_map_status
    status = mapper(raw)
    data = order.model_dump()
    data["status"] = status if status != "UNKNOWN" else "RECOVERED"
    data["broker_order_id"] = str(raw.get("id") or order.broker_order_id or "")
    data["filled_quantity"] = float(raw.get("filled_qty") or raw.get("filled_quantity") or 0)
    if raw.get("filled_avg_price") is not None:
        data["avg_fill_price"] = float(raw["filled_avg_price"])
    data["metadata"] = {**dict(order.metadata or {}), "recover_query": True}
    return ControlledOrder.model_validate(data)


def _default_map_status(raw: dict[str, Any]) -> str:
    st = str(raw.get("status") or "UNKNOWN").upper()
    mapping = {
        "NEW": "ACCEPTED",
        "ACCEPTED": "ACCEPTED",
        "PARTIALLY_FILLED": "PARTIALLY_FILLED",
        "FILLED": "FILLED",
        "CANCELED": "EXPIRED",
        "CANCELLED": "EXPIRED",
        "REJECTED": "REJECTED",
        "EXPIRED": "EXPIRED",
    }
    return mapping.get(st, "UNKNOWN")
