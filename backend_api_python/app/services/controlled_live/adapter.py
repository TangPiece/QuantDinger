"""Phase 7C：经 OrderExecutionGateway 薄封装 Broker submit。"""

from __future__ import annotations

from typing import Any, Callable

from app.services.oms.protocol import Order
from app.services.shadow_trading.gateway import OrderExecutionGateway


def submit_via_gateway(
    *,
    environment: str,
    order: Order,
    broker_port: Any,
    gateway: OrderExecutionGateway | None = None,
) -> Any:
    """LIVE_CONTROLLED 唯一允许的 real submit 路径。"""
    gw = gateway or OrderExecutionGateway()

    def _do_submit(o: Order) -> Any:
        fn = getattr(broker_port, "submit_order", None)
        if not callable(fn):
            raise RuntimeError("broker_port.submit_order required")
        return fn(o)

    return gw.submit_real(environment, order, broker_port, submit_fn=_do_submit)


def query_by_client_order_id(broker_port: Any, client_order_id: str) -> dict[str, Any]:
    """Timeout recover：只读查询，不经 Gateway POST。"""
    fn = getattr(broker_port, "get_order_by_client_id", None)
    if not callable(fn):
        raise RuntimeError("broker_port.get_order_by_client_id required")
    return fn(client_order_id)
