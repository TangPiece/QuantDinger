"""AlpacaPaperAdapter：仅 Paper API；禁止 Live / live_trading Domain。"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.services.oms.protocol import (
    CancelRequest,
    ExecutionReport,
    Order,
    ReplaceRequest,
)

from ...credentials import has_alpaca_paper_credentials, load_alpaca_paper_credentials
from ...errors import AdapterErrorCode, BrokerAdapterError
from ...protocol import (
    BrokerAccountView,
    BrokerCapabilities,
    BrokerOrderView,
    BrokerPositionView,
    ExecutionMode,
)
from .mapping import alpaca_order_to_report, order_to_alpaca_payload
from .transport import AlpacaPaperTransport


class AlpacaPaperAdapter:
    """Reference Adapter：execution_mode=ALPACA_PAPER。"""

    broker_id: str = "alpaca_paper"
    execution_mode: ExecutionMode = "ALPACA_PAPER"

    def __init__(
        self,
        *,
        transport: AlpacaPaperTransport | None = None,
        credentials: Mapping[str, str] | None = None,
    ) -> None:
        self.capabilities = BrokerCapabilities(
            supports_market_order=True,
            supports_limit_order=True,
            supports_cancel=True,
            supports_replace=True,
            supports_websocket=True,
            supports_paper=True,
            supports_fractional=True,
        )
        self._transport = transport
        self._credentials = dict(credentials) if credentials else None
        self._connected = False
        self._order_map: dict[str, str] = {}  # client_order_id → broker_order_id

    def connect(self) -> None:
        if self._transport is None:
            if not has_alpaca_paper_credentials() and not self._credentials:
                raise BrokerAdapterError(
                    "Alpaca Paper credentials missing",
                    code=AdapterErrorCode.AUTH_FAILED,
                )
            self._transport = AlpacaPaperTransport(self._credentials)
        # 探测账户（失败则抛）
        self._transport.get_account()
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def set_prices(self, prices: Mapping[str, float]) -> None:
        """Alpaca 不使用本地价；no-op。"""
        return None

    def _ensure(self) -> AlpacaPaperTransport:
        if not self._connected or self._transport is None:
            raise BrokerAdapterError(
                "not connected", code=AdapterErrorCode.NOT_CONNECTED
            )
        return self._transport

    # BrokerPort
    def submit(self, order: Order) -> ExecutionReport:
        return self.submit_order(order)

    def cancel(self, order: Order, *, reason: str = "") -> ExecutionReport:
        return self.cancel_order(
            order,
            CancelRequest(
                request_id=f"cxl_{order.order_id[:12]}",
                order_id=order.order_id,
                reason=reason,
            ),
        )

    def replace(
        self,
        order: Order,
        *,
        quantity: Optional[float] = None,
        limit_price: Optional[float] = None,
    ) -> ExecutionReport:
        return self.replace_order(
            order,
            ReplaceRequest(
                request_id=f"rpl_{order.order_id[:12]}",
                order_id=order.order_id,
                quantity=quantity,
                limit_price=limit_price,
            ),
        )

    def submit_order(self, order: Order) -> ExecutionReport:
        tr = self._ensure()
        ot = str(order.order_type).upper()
        if ot == "MARKET" and not self.capabilities.supports_market_order:
            return ExecutionReport(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="REJECT",
                message=AdapterErrorCode.UNSUPPORTED_ORDER_TYPE.value,
            )
        try:
            raw = tr.submit_order(order_to_alpaca_payload(order))
        except BrokerAdapterError as exc:
            if exc.code == AdapterErrorCode.NETWORK_UNKNOWN:
                return ExecutionReport(
                    order_id=order.order_id,
                    client_order_id=order.client_order_id,
                    status="UNKNOWN",
                    message=str(exc),
                )
            return ExecutionReport(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="REJECT",
                message=str(exc),
            )
        report = alpaca_order_to_report(raw, order=order)
        if report.broker_order_id:
            self._order_map[order.client_order_id] = report.broker_order_id
        return report

    def cancel_order(self, order: Order, request: CancelRequest) -> ExecutionReport:
        tr = self._ensure()
        boid = order.broker_order_id or self._order_map.get(order.client_order_id, "")
        if not boid:
            return ExecutionReport(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="REJECT",
                message="missing broker_order_id",
            )
        try:
            raw = tr.cancel_order(boid)
            if not raw:
                raw = {"id": boid, "status": "canceled", "client_order_id": order.client_order_id}
        except BrokerAdapterError as exc:
            if exc.code == AdapterErrorCode.NETWORK_UNKNOWN:
                return ExecutionReport(
                    order_id=order.order_id,
                    client_order_id=order.client_order_id,
                    broker_order_id=boid,
                    status="UNKNOWN",
                    message=str(exc),
                )
            raise
        return alpaca_order_to_report(raw, order=order)

    def replace_order(self, order: Order, request: ReplaceRequest) -> ExecutionReport:
        tr = self._ensure()
        boid = order.broker_order_id or self._order_map.get(order.client_order_id, "")
        if not boid:
            return ExecutionReport(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="REJECT",
                message="missing broker_order_id",
            )
        payload: dict[str, Any] = {}
        if request.quantity is not None:
            payload["qty"] = str(request.quantity)
        if request.limit_price is not None:
            payload["limit_price"] = str(request.limit_price)
        try:
            raw = tr.replace_order(boid, payload)
        except BrokerAdapterError as exc:
            if exc.code == AdapterErrorCode.NETWORK_UNKNOWN:
                return ExecutionReport(
                    order_id=order.order_id,
                    client_order_id=order.client_order_id,
                    broker_order_id=boid,
                    status="UNKNOWN",
                    message=str(exc),
                )
            raise
        return alpaca_order_to_report(raw, order=order)

    def get_order(self, *, client_order_id: str) -> BrokerOrderView:
        tr = self._ensure()
        raw = tr.get_order_by_client_id(client_order_id)
        return BrokerOrderView(
            client_order_id=str(raw.get("client_order_id") or client_order_id),
            broker_order_id=str(raw.get("id") or ""),
            instrument_key=str(raw.get("symbol") or ""),
            side=str(raw.get("side") or "").upper(),
            order_type=str(raw.get("type") or "").upper(),
            quantity=float(raw.get("qty") or 0),
            filled_quantity=float(raw.get("filled_qty") or 0),
            limit_price=float(raw["limit_price"])
            if raw.get("limit_price") not in (None, "")
            else None,
            status=str(raw.get("status") or ""),
            avg_fill_price=float(raw.get("filled_avg_price") or 0 or 0),
        )

    def get_open_orders(self) -> list[BrokerOrderView]:
        tr = self._ensure()
        out: list[BrokerOrderView] = []
        for raw in tr.list_open_orders():
            out.append(
                BrokerOrderView(
                    client_order_id=str(raw.get("client_order_id") or ""),
                    broker_order_id=str(raw.get("id") or ""),
                    instrument_key=str(raw.get("symbol") or ""),
                    side=str(raw.get("side") or "").upper(),
                    order_type=str(raw.get("type") or "").upper(),
                    quantity=float(raw.get("qty") or 0),
                    filled_quantity=float(raw.get("filled_qty") or 0),
                    status=str(raw.get("status") or ""),
                    avg_fill_price=float(raw.get("filled_avg_price") or 0 or 0),
                )
            )
        return out

    def get_positions(self) -> list[BrokerPositionView]:
        tr = self._ensure()
        out: list[BrokerPositionView] = []
        for raw in tr.get_positions():
            qty = float(raw.get("qty") or 0)
            out.append(
                BrokerPositionView(
                    instrument_key=str(raw.get("symbol") or ""),
                    quantity=qty,
                    available_quantity=qty,
                    avg_cost=float(raw.get("avg_entry_price") or 0 or 0),
                    market_value=float(raw.get("market_value") or 0 or 0),
                    side=str(raw.get("side") or "long").upper(),
                )
            )
        return out

    def get_account(self) -> BrokerAccountView:
        tr = self._ensure()
        raw = tr.get_account()
        return BrokerAccountView(
            broker_id=self.broker_id,
            account_id=str(raw.get("id") or ""),
            currency=str(raw.get("currency") or "USD"),
            cash=float(raw.get("cash") or 0 or 0),
            buying_power=float(raw.get("buying_power") or 0 or 0),
            equity=float(raw.get("equity") or 0 or 0),
            status=str(raw.get("status") or "ACTIVE"),
            metadata={"paper": True},
        )
