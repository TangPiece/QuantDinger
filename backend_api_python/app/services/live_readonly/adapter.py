"""Phase 7A：LiveReadonlyAdapter — 只读查询；写单硬拒。"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.services.broker_adapter.errors import AdapterErrorCode, BrokerAdapterError
from app.services.broker_adapter.protocol import (
    BrokerAccountView,
    BrokerOrderView,
    BrokerPositionView,
)
from app.services.oms.protocol import CancelRequest, ExecutionReport, Order, ReplaceRequest

from .credentials import has_alpaca_live_credentials, load_alpaca_live_credentials
from .gate import require_production_ready
from .protocol import LiveReadonlyCapabilities
from .transport import AlpacaLiveReadonlyTransport, FakeLiveReadonlyTransport


def _forbid_write(operation: str) -> None:
    """所有 BrokerPort / 写单 API 统一硬拒。"""
    raise BrokerAdapterError(
        f"LIVE_READONLY: {operation} forbidden",
        code=AdapterErrorCode.LIVE_READONLY_FORBIDDEN,
    )


class LiveReadonlyAdapter:
    """Alpaca Live 只读 Adapter；execution_mode 语义为 LIVE_READONLY。"""

    broker_id: str = "alpaca_live_readonly"
    execution_mode: str = "LIVE_READONLY"

    def __init__(
        self,
        *,
        transport: Any | None = None,
        credentials: Mapping[str, str] | None = None,
        registry: Any = None,
        skip_production_gate: bool = False,
    ) -> None:
        self.capabilities = LiveReadonlyCapabilities()
        self._transport = transport
        self._credentials = dict(credentials) if credentials else None
        self._registry = registry
        self._skip_production_gate = skip_production_gate
        self._connected = False

    def connect(self) -> None:
        """连接前校验 PRODUCTION_READY + 凭证。"""
        if not self._skip_production_gate:
            require_production_ready(self._registry)
        if self._transport is None:
            if not has_alpaca_live_credentials() and not self._credentials:
                raise BrokerAdapterError(
                    "Alpaca Live credentials missing (ALPACA_LIVE_*)",
                    code=AdapterErrorCode.AUTH_FAILED,
                )
            self._transport = AlpacaLiveReadonlyTransport(self._credentials)
        self._transport.get_account()
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def _ensure(self) -> Any:
        if not self._connected or self._transport is None:
            raise BrokerAdapterError(
                "not connected", code=AdapterErrorCode.NOT_CONNECTED
            )
        return self._transport

    # --- BrokerPort 写路径：硬拒 ---
    def submit(self, order: Order) -> ExecutionReport:
        _forbid_write("submit")

    def cancel(self, order: Order, *, reason: str = "") -> ExecutionReport:
        _forbid_write("cancel")

    def replace(
        self,
        order: Order,
        *,
        quantity: Optional[float] = None,
        limit_price: Optional[float] = None,
    ) -> ExecutionReport:
        _forbid_write("replace")

    def submit_order(self, order: Order) -> ExecutionReport:
        _forbid_write("submit_order")

    def cancel_order(self, order: Order, request: CancelRequest) -> ExecutionReport:
        _forbid_write("cancel_order")

    def replace_order(self, order: Order, request: ReplaceRequest) -> ExecutionReport:
        _forbid_write("replace_order")

    # --- 只读查询 ---
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
            metadata={"live_readonly": True},
        )

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
            status=str(raw.get("status") or ""),
            avg_fill_price=float(raw.get("filled_avg_price") or 0 or 0),
        )

    def recent_executions(self, *, limit: int = 500) -> list[dict[str, Any]]:
        """供 6F build_broker_snapshot 采集成交。"""
        tr = self._ensure()
        if not hasattr(tr, "list_activities"):
            return []
        rows = tr.list_activities(activity_type="FILL", page_size=min(limit, 100))
        out: list[dict[str, Any]] = []
        for raw in rows[:limit]:
            out.append(
                {
                    "broker_execution_id": str(raw.get("id") or raw.get("activity_id") or ""),
                    "client_order_id": str(raw.get("order_id") or ""),
                    "order_id": str(raw.get("order_id") or ""),
                    "quantity": float(raw.get("qty") or raw.get("cum_qty") or 0),
                    "price": float(raw.get("price") or raw.get("fill_price") or 0),
                    "fee": 0.0,
                    "ts": str(raw.get("transaction_time") or raw.get("date") or ""),
                    "metadata": {"source": "alpaca_activity"},
                }
            )
        return out


def fake_adapter(**kwargs: Any) -> LiveReadonlyAdapter:
    """测试工厂：Fake transport + 跳过生产门（仍需显式 connect）。"""
    ad = LiveReadonlyAdapter(
        transport=FakeLiveReadonlyTransport(**kwargs),
        skip_production_gate=True,
    )
    return ad
