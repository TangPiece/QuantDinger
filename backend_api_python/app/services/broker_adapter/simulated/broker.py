"""SimulatedBrokerAdapter：Fake REST + WS，SANDBOX/SHADOW。"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

from app.services.oms.protocol import (
    CancelRequest,
    ExecutionReport,
    Order,
    ReplaceRequest,
)

from ..dedup import ExecutionDeduper
from ..errors import AdapterErrorCode, BrokerAdapterError
from ..execution_bridge import event_to_execution_report
from ..protocol import (
    BrokerAccountView,
    BrokerCapabilities,
    BrokerOrderView,
    BrokerPositionView,
    ExecutionMode,
)
from .rest import SimulatedRestBook
from .ws import SimulatedWebSocket


class SimulatedBrokerAdapter:
    """SANDBOX/SHADOW：可注入断线、重复事件、submit 后 UNKNOWN。"""

    broker_id: str = "simulated"

    def __init__(
        self,
        *,
        execution_mode: ExecutionMode = "SANDBOX",
        prices: Mapping[str, float] | None = None,
        deduper: ExecutionDeduper | None = None,
    ) -> None:
        if execution_mode == "LIVE":  # type: ignore[comparison-overlap]
            raise BrokerAdapterError(
                "LIVE not enabled in Phase 6E",
                code=AdapterErrorCode.LIVE_FORBIDDEN,
            )
        if execution_mode not in ("SANDBOX", "SHADOW", "PAPER"):
            # PAPER 也允许用 simulated；通常用 PaperBrokerAdapter
            pass
        self.execution_mode = execution_mode  # type: ignore[assignment]
        self.capabilities = BrokerCapabilities(
            supports_market_order=True,
            supports_limit_order=True,
            supports_cancel=True,
            supports_replace=True,
            supports_websocket=True,
            supports_paper=True,
        )
        self._rest = SimulatedRestBook(prices=prices, broker_id=self.broker_id)
        self._ws = SimulatedWebSocket(broker_id=self.broker_id)
        self._deduper = deduper or ExecutionDeduper()
        self._connected = False
        self._cash = 1_000_000.0
        self._positions: dict[str, float] = {}

    def connect(self) -> None:
        self._connected = True
        self._ws.connect()
        self._ws.subscribe_executions()

    def disconnect(self) -> None:
        self._connected = False
        self._ws.disconnect()

    def set_prices(self, prices: Mapping[str, float]) -> None:
        self._rest.set_prices(prices)

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
        meta = dict(order.metadata or {})
        inject = dict(meta.get("simulated") or meta.get("paper_broker") or meta)
        if inject.get("ws_disconnect_after_n") is not None:
            self._ws.configure_disconnect_after(int(inject["ws_disconnect_after_n"]))

        report = self._rest.submit(order)
        # 推送 WS 事件（含 duplicate 注入）
        for fill in report.fills:
            exec_id = str(
                (fill.metadata or {}).get("broker_execution_id") or fill.fill_id
            )
            ev_type = "FILL" if report.status == "FILL" else "PARTIAL"
            self._ws.push_raw(
                broker_execution_id=exec_id,
                event_type=ev_type,
                client_order_id=order.client_order_id,
                broker_order_id=report.broker_order_id,
                order_id=order.order_id,
                quantity=float(fill.quantity),
                price=float(fill.price),
                filled_quantity=float(report.filled_quantity),
                remaining_quantity=float(report.remaining_quantity),
            )
            if inject.get("duplicate_execution"):
                # 故意重复推送同一 execution id
                self._ws.push_raw(
                    broker_execution_id=exec_id,
                    event_type=ev_type,
                    client_order_id=order.client_order_id,
                    broker_order_id=report.broker_order_id,
                    order_id=order.order_id,
                    quantity=float(fill.quantity),
                    price=float(fill.price),
                    filled_quantity=float(report.filled_quantity),
                    remaining_quantity=float(report.remaining_quantity),
                    message="duplicate",
                )
        return report

    def cancel_order(self, order: Order, request: CancelRequest) -> ExecutionReport:
        return self._rest.cancel(order, reason=request.reason)

    def replace_order(self, order: Order, request: ReplaceRequest) -> ExecutionReport:
        return self._rest.replace(
            order, quantity=request.quantity, limit_price=request.limit_price
        )

    def get_order(self, *, client_order_id: str) -> BrokerOrderView:
        try:
            row = self._rest.get_order(client_order_id)
        except KeyError as exc:
            raise BrokerAdapterError(
                f"order not found: {client_order_id}",
                code=AdapterErrorCode.NOT_FOUND,
            ) from exc
        o: Order = row["order"]
        return BrokerOrderView(
            client_order_id=o.client_order_id,
            broker_order_id=str(row.get("broker_order_id") or ""),
            order_id=o.order_id,
            instrument_key=o.instrument_key,
            side=str(o.side),
            order_type=str(o.order_type),
            quantity=float(o.quantity),
            filled_quantity=float(row.get("filled") or 0),
            limit_price=o.limit_price,
            status=str(row.get("status") or ""),
            avg_fill_price=float(row.get("avg_price") or 0),
        )

    def recover_unknown(self, order: Order) -> ExecutionReport:
        """UNKNOWN → get_order → ExecutionReport（禁止自动重下单）。"""
        return self._rest.recover_report(order)

    def get_open_orders(self) -> list[BrokerOrderView]:
        out: list[BrokerOrderView] = []
        for row in self._rest.list_open():
            o: Order = row["order"]
            out.append(
                BrokerOrderView(
                    client_order_id=o.client_order_id,
                    broker_order_id=str(row.get("broker_order_id") or ""),
                    order_id=o.order_id,
                    instrument_key=o.instrument_key,
                    side=str(o.side),
                    order_type=str(o.order_type),
                    quantity=float(o.quantity),
                    filled_quantity=float(row.get("filled") or 0),
                    limit_price=o.limit_price,
                    status=str(row.get("status") or ""),
                    avg_fill_price=float(row.get("avg_price") or 0),
                )
            )
        return out

    def get_positions(self) -> list[BrokerPositionView]:
        return [
            BrokerPositionView(
                instrument_key=k,
                quantity=v,
                available_quantity=v,
                side="LONG" if v >= 0 else "SHORT",
            )
            for k, v in self._positions.items()
        ]

    def get_account(self) -> BrokerAccountView:
        return BrokerAccountView(
            broker_id=self.broker_id,
            account_id="sim",
            cash=self._cash,
            buying_power=self._cash,
            equity=self._cash,
            status="ACTIVE",
        )

    def reconnect_ws(self) -> None:
        """断线恢复：reconnect + resubscribe + REST 补单。"""
        self._ws.reconnect_and_resubscribe()
        # 补推 recent executions（可能含已送达；由 dedup 过滤）
        for ex in self._rest.recent_executions():
            self._ws.push_raw(
                broker_execution_id=str(ex["broker_execution_id"]),
                event_type="FILL",
                client_order_id=str(ex.get("client_order_id") or ""),
                quantity=float(ex.get("quantity") or 0),
                price=float(ex.get("price") or 0),
                message="replay after reconnect",
            )

    def pump_events(
        self, callback: Callable[[ExecutionReport], None]
    ) -> int:
        """将 WS 队列转为 ExecutionReport 并回调（带 dedup）。"""
        n = 0
        for ev in self._ws.drain():
            if not self._deduper.try_accept(ev.broker_id, ev.broker_execution_id):
                continue
            report = event_to_execution_report(ev, broker="simulated")
            callback(report)
            n += 1
        return n

    @property
    def ws(self) -> SimulatedWebSocket:
        return self._ws


# package marker
