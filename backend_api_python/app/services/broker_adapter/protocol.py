"""Phase 6E：Broker Adapter Domain（Contract；停在 Paper / Fake / Alpaca Paper）。"""

from __future__ import annotations

from typing import Any, Literal, Optional, Protocol, runtime_checkable

from pydantic import Field

from app.services.oms.protocol import (
    CancelRequest,
    ExecutionReport,
    Order,
    ReplaceRequest,
)
from app.services.research_data.contracts import _ContractModel

ENGINE_VERSION = "qd_broker_adapter@1"

ExecutionMode = Literal["PAPER", "SANDBOX", "SHADOW", "ALPACA_PAPER"]


class BrokerCapabilities(_ContractModel):
    """Broker 能力声明；OMS 提交前校验，不调用不支持的 API。"""

    supports_market_order: bool = True
    supports_limit_order: bool = True
    supports_cancel: bool = True
    supports_replace: bool = True
    supports_fractional: bool = False
    supports_short: bool = False
    supports_margin: bool = False
    supports_websocket: bool = False
    supports_streaming_positions: bool = False
    supports_paper: bool = True


class BrokerSession(_ContractModel):
    """Adapter 会话元数据。"""

    session_id: str
    broker_id: str
    execution_mode: ExecutionMode = "PAPER"
    status: str = "DISCONNECTED"  # CONNECTED | DISCONNECTED | RECONNECTING
    engine_version: str = ENGINE_VERSION
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrokerAccountView(_ContractModel):
    """Broker 账户只读视图（不写 6B Position）。"""

    broker_id: str = ""
    account_id: str = ""
    currency: str = "USD"
    cash: float = 0.0
    buying_power: float = 0.0
    equity: float = 0.0
    status: str = "ACTIVE"
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrokerBalanceView(_ContractModel):
    """资金余额视图。"""

    currency: str = "USD"
    cash: float = 0.0
    available: float = 0.0
    frozen: float = 0.0


class BrokerPositionView(_ContractModel):
    """Broker 持仓视图（≠ QuantDinger Position；供 6F 对账）。"""

    instrument_key: str = ""
    quantity: float = 0.0
    available_quantity: float = 0.0
    avg_cost: float = 0.0
    market_value: float = 0.0
    side: str = "LONG"
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrokerOrderView(_ContractModel):
    """Broker 侧订单查询视图。"""

    client_order_id: str = ""
    broker_order_id: str = ""
    order_id: str = ""
    instrument_key: str = ""
    side: str = "BUY"
    order_type: str = "MARKET"
    quantity: float = 0.0
    filled_quantity: float = 0.0
    limit_price: Optional[float] = None
    status: str = ""  # broker raw 或已映射摘要
    avg_fill_price: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class BrokerAdapter(Protocol):
    """统一 Broker 契约；OMS 只消费 ExecutionReport。"""

    broker_id: str
    capabilities: BrokerCapabilities
    execution_mode: ExecutionMode

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def submit_order(self, order: Order) -> ExecutionReport: ...

    def cancel_order(
        self, order: Order, request: CancelRequest
    ) -> ExecutionReport: ...

    def replace_order(
        self, order: Order, request: ReplaceRequest
    ) -> ExecutionReport: ...

    def get_order(self, *, client_order_id: str) -> BrokerOrderView: ...

    def get_open_orders(self) -> list[BrokerOrderView]: ...

    def get_positions(self) -> list[BrokerPositionView]: ...

    def get_account(self) -> BrokerAccountView: ...


__all__ = [
    "ENGINE_VERSION",
    "BrokerAdapter",
    "BrokerAccountView",
    "BrokerBalanceView",
    "BrokerCapabilities",
    "BrokerOrderView",
    "BrokerPositionView",
    "BrokerSession",
    "CancelRequest",
    "ExecutionMode",
    "ExecutionReport",
    "Order",
    "ReplaceRequest",
]
