"""BrokerAdapterService：选 adapter、session、event pump。"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from app.services.oms.protocol import ExecutionReport, Order
from app.services.research_data.registry import ResearchRegistry

from .cycle import pump_adapter_events, submit_via_adapter
from .dedup import ExecutionDeduper
from .errors import AdapterErrorCode, BrokerAdapterError
from .paper_adapter import PaperBrokerAdapter
from .protocol import ENGINE_VERSION, BrokerAdapter, ExecutionMode
from .raw_store import BrokerRawStore
from .session import SessionManager
from .simulated import SimulatedBrokerAdapter
from .writers import BrokerWriter


class BrokerAdapterService:
    """Broker Adapter 编排；Phase 6E 无 LIVE。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        adapter: BrokerAdapter | None = None,
        execution_mode: ExecutionMode = "PAPER",
        prices: Mapping[str, float] | None = None,
        raw_store: BrokerRawStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._writer = BrokerWriter(registry, raw_store=raw_store)
        self._deduper = ExecutionDeduper(
            try_record=lambda b, e: self._writer.try_dedup(b, e)
        )
        self._sessions = SessionManager(self._writer)
        mode = str(execution_mode).upper()
        if mode == "LIVE":
            raise BrokerAdapterError(
                "LIVE not enabled in Phase 6E",
                code=AdapterErrorCode.LIVE_FORBIDDEN,
            )
        if adapter is not None:
            self._adapter = adapter
        elif mode in ("SANDBOX", "SHADOW"):
            self._adapter = SimulatedBrokerAdapter(
                execution_mode=mode,  # type: ignore[arg-type]
                prices=prices,
                deduper=self._deduper,
            )
        elif mode == "ALPACA_PAPER":
            from .adapters.alpaca.paper_adapter import AlpacaPaperAdapter

            self._adapter = AlpacaPaperAdapter()
        else:
            self._adapter = PaperBrokerAdapter(prices=prices)
        self.engine_version = ENGINE_VERSION

    @property
    def adapter(self) -> BrokerAdapter:
        return self._adapter

    def connect(self):
        return self._sessions.connect(self._adapter)

    def disconnect(self) -> None:
        self._sessions.disconnect(self._adapter)

    def health(self) -> dict:
        return self._sessions.health(self._adapter)

    def submit_order(self, order: Order) -> ExecutionReport:
        return submit_via_adapter(
            self._adapter,
            order,
            writer=self._writer,
            deduper=self._deduper,
        )

    def start_event_pump(
        self, callback: Callable[[ExecutionReport], None]
    ) -> int:
        return pump_adapter_events(
            self._adapter,
            callback,
            writer=self._writer,
            deduper=self._deduper,
        )

    def recover_order(self, order: Order) -> ExecutionReport:
        """UNKNOWN 恢复：query broker，禁止自动重下单。"""
        if hasattr(self._adapter, "recover_unknown"):
            return self._adapter.recover_unknown(order)  # type: ignore[attr-defined]
        view = self._adapter.get_order(client_order_id=order.client_order_id)
        from .execution_bridge import order_view_to_execution_report

        return order_view_to_execution_report(
            order=order,
            broker_status=view.status,
            broker_order_id=view.broker_order_id,
            filled_quantity=view.filled_quantity,
            avg_price=view.avg_fill_price,
            broker=getattr(self._adapter, "broker_id", "simulated"),
        )


__all__ = ["BrokerAdapterService", "ENGINE_VERSION"]
