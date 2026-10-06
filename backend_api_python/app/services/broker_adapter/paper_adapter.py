"""PaperBrokerAdapter：委托 oms.PaperBroker，实现 BrokerAdapter + BrokerPort。"""

from __future__ import annotations

from typing import Mapping, Optional

from app.services.oms.paper_broker import PaperBroker
from app.services.oms.protocol import (
    CancelRequest,
    ExecutionReport,
    Order,
    ReplaceRequest,
)

from .errors import AdapterErrorCode, BrokerAdapterError
from .protocol import (
    ENGINE_VERSION,
    BrokerAccountView,
    BrokerCapabilities,
    BrokerOrderView,
    BrokerPositionView,
    ExecutionMode,
)


class PaperBrokerAdapter:
    """PAPER execution_mode；统一 submit/cancel/replace 签名。"""

    broker_id: str = "paper"
    execution_mode: ExecutionMode = "PAPER"

    def __init__(
        self,
        paper: PaperBroker | None = None,
        *,
        prices: Mapping[str, float] | None = None,
    ) -> None:
        self._paper = paper or PaperBroker(prices=prices)
        self.capabilities = BrokerCapabilities(
            supports_market_order=True,
            supports_limit_order=True,
            supports_cancel=True,
            supports_replace=True,
            supports_websocket=False,
            supports_paper=True,
        )
        self._connected = False
        self._orders: dict[str, Order] = {}
        self._engine_version = ENGINE_VERSION

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def set_prices(self, prices: Mapping[str, float]) -> None:
        self._paper.set_prices(prices)

    def _ensure_capability(self, order: Order) -> Optional[ExecutionReport]:
        ot = str(order.order_type).upper()
        if ot == "MARKET" and not self.capabilities.supports_market_order:
            return ExecutionReport(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="REJECT",
                message=AdapterErrorCode.UNSUPPORTED_ORDER_TYPE.value,
            )
        if ot == "LIMIT" and not self.capabilities.supports_limit_order:
            return ExecutionReport(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="REJECT",
                message=AdapterErrorCode.UNSUPPORTED_ORDER_TYPE.value,
            )
        return None

    # --- BrokerPort ---
    def submit(self, order: Order) -> ExecutionReport:
        return self.submit_order(order)

    def cancel(self, order: Order, *, reason: str = "") -> ExecutionReport:
        req = CancelRequest(
            request_id=f"cxl_{order.order_id[:12]}",
            order_id=order.order_id,
            reason=reason,
        )
        return self.cancel_order(order, req)

    def replace(
        self,
        order: Order,
        *,
        quantity: Optional[float] = None,
        limit_price: Optional[float] = None,
    ) -> ExecutionReport:
        req = ReplaceRequest(
            request_id=f"rpl_{order.order_id[:12]}",
            order_id=order.order_id,
            quantity=quantity,
            limit_price=limit_price,
        )
        return self.replace_order(order, req)

    # --- BrokerAdapter ---
    def submit_order(self, order: Order) -> ExecutionReport:
        bad = self._ensure_capability(order)
        if bad is not None:
            return bad
        report = self._paper.submit(order)
        report = report.model_copy(
            update={
                "client_order_id": order.client_order_id,
                "order_id": order.order_id or report.order_id,
            }
        )
        self._orders[order.client_order_id] = order.model_copy(
            update={"broker_order_id": report.broker_order_id or ""}
        )
        return report

    def cancel_order(self, order: Order, request: CancelRequest) -> ExecutionReport:
        if not self.capabilities.supports_cancel:
            return ExecutionReport(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="REJECT",
                message=AdapterErrorCode.UNSUPPORTED_OPERATION.value,
            )
        report = self._paper.cancel(order, reason=request.reason)
        return report.model_copy(
            update={"client_order_id": order.client_order_id}
        )

    def replace_order(self, order: Order, request: ReplaceRequest) -> ExecutionReport:
        if not self.capabilities.supports_replace:
            return ExecutionReport(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="REJECT",
                message=AdapterErrorCode.UNSUPPORTED_OPERATION.value,
            )
        report = self._paper.replace(
            order, quantity=request.quantity, limit_price=request.limit_price
        )
        return report.model_copy(
            update={"client_order_id": order.client_order_id}
        )

    def get_order(self, *, client_order_id: str) -> BrokerOrderView:
        order = self._orders.get(client_order_id)
        if order is None:
            raise BrokerAdapterError(
                f"order not found: {client_order_id}",
                code=AdapterErrorCode.NOT_FOUND,
            )
        return BrokerOrderView(
            client_order_id=order.client_order_id,
            broker_order_id=order.broker_order_id,
            order_id=order.order_id,
            instrument_key=order.instrument_key,
            side=str(order.side),
            order_type=str(order.order_type),
            quantity=float(order.quantity),
            filled_quantity=float(order.filled_quantity),
            limit_price=order.limit_price,
            status=str(order.status),
            avg_fill_price=float(order.avg_fill_price),
        )

    def get_open_orders(self) -> list[BrokerOrderView]:
        out: list[BrokerOrderView] = []
        for cid in self._orders:
            try:
                out.append(self.get_order(client_order_id=cid))
            except BrokerAdapterError:
                continue
        return out

    def get_positions(self) -> list[BrokerPositionView]:
        return []

    def get_account(self) -> BrokerAccountView:
        return BrokerAccountView(
            broker_id=self.broker_id,
            account_id="paper",
            currency="USD",
            status="ACTIVE",
            metadata={"engine_version": self._engine_version},
        )
