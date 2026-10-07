"""Phase 7C：Alpaca Controlled Live Adapter — LIMIT submit only；cancel/replace 硬拒。"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.services.broker_adapter.errors import AdapterErrorCode, BrokerAdapterError
from app.services.oms.protocol import Order

from .live_trading_transport import AlpacaLiveTradingTransport

BROKER_ID = "alpaca_live_controlled"


def _forbid_cancel_replace(action: str) -> None:
    raise BrokerAdapterError(
        f"{action} forbidden in Phase 7C controlled live",
        code=AdapterErrorCode.LIVE_FORBIDDEN,
    )


class AlpacaControlledLiveAdapter:
    """真实 Live POST（opt-in 由 config.allow_real_submit + 凭证控制）。"""

    broker_id = BROKER_ID
    execution_mode = "LIVE_CONTROLLED"

    def __init__(self, transport: AlpacaLiveTradingTransport | None = None) -> None:
        self._transport = transport or AlpacaLiveTradingTransport()

    def submit_order(self, order: Order) -> dict[str, Any]:
        if str(order.order_type or "").upper() != "LIMIT":
            raise BrokerAdapterError(
                "only LIMIT orders allowed",
                code=AdapterErrorCode.REJECTED,
            )
        payload = {
            "symbol": _symbol(order),
            "qty": str(order.quantity),
            "side": str(order.side).lower(),
            "type": "limit",
            "limit_price": str(order.limit_price),
            "time_in_force": str(order.tif or "day").lower(),
            "client_order_id": order.client_order_id,
        }
        return self._transport.submit_order(payload)

    def cancel_order(self, *_args: Any, **_kwargs: Any) -> Any:
        _forbid_cancel_replace("cancel_order")

    def replace_order(self, *_args: Any, **_kwargs: Any) -> Any:
        _forbid_cancel_replace("replace_order")

    def cancel(self, *_args: Any, **_kwargs: Any) -> Any:
        _forbid_cancel_replace("cancel")

    def replace(self, *_args: Any, **_kwargs: Any) -> Any:
        _forbid_cancel_replace("replace")

    def get_order_by_client_id(self, client_order_id: str) -> dict[str, Any]:
        return self._transport.get_order_by_client_id(client_order_id)


class FakeControlledLiveAdapter:
    """CI 默认 Fake：跟踪 submit_count；可模拟 UNKNOWN。"""

    broker_id = "alpaca_live_controlled_fake"
    execution_mode = "LIVE_CONTROLLED"

    def __init__(
        self,
        *,
        existing_by_client: Mapping[str, dict[str, Any]] | None = None,
        next_submit_raises_unknown: bool = False,
    ) -> None:
        self.submit_count = 0
        self._orders: dict[str, dict[str, Any]] = dict(existing_by_client or {})
        self._next_unknown = next_submit_raises_unknown

    def submit_order(self, order: Order) -> dict[str, Any]:
        if str(order.order_type or "").upper() != "LIMIT":
            raise BrokerAdapterError("only LIMIT", code=AdapterErrorCode.REJECTED)
        self.submit_count += 1
        if self._next_unknown:
            raise BrokerAdapterError(
                "simulated network unknown",
                code=AdapterErrorCode.NETWORK_UNKNOWN,
            )
        sym = _symbol(order)
        rec = {
            "id": f"brk_{order.client_order_id}",
            "client_order_id": order.client_order_id,
            "symbol": sym,
            "status": "accepted",
            "filled_qty": "0",
        }
        self._orders[order.client_order_id] = rec
        return rec

    def cancel_order(self, *_a: Any, **_k: Any) -> Any:
        _forbid_cancel_replace("cancel_order")

    def replace_order(self, *_a: Any, **_k: Any) -> Any:
        _forbid_cancel_replace("replace_order")

    def get_order_by_client_id(self, client_order_id: str) -> dict[str, Any]:
        if client_order_id in self._orders:
            return dict(self._orders[client_order_id])
        return {"status": "unknown", "client_order_id": client_order_id}


def _symbol(order: Order) -> str:
    key = str(order.instrument_key or "")
    if ":" in key:
        return key.split(":", 1)[1].upper()
    meta = dict(order.metadata or {})
    return str(meta.get("symbol") or key).upper()
