"""OMS 侧 Broker 端口：submit/cancel/replace → ExecutionReport（与 PaperBroker 同形）。"""

from __future__ import annotations

from typing import Mapping, Optional, Protocol, runtime_checkable

from .protocol import CancelRequest, ExecutionReport, Order, ReplaceRequest


@runtime_checkable
class BrokerPort(Protocol):
    """6E：OMS 只依赖此端口；禁止在 OMS 内写券商 raw status。"""

    def submit(self, order: Order) -> ExecutionReport:
        """提交订单，返回归一化 ExecutionReport。"""
        ...

    def cancel(self, order: Order, *, reason: str = "") -> ExecutionReport:
        """撤单。"""
        ...

    def replace(
        self,
        order: Order,
        *,
        quantity: Optional[float] = None,
        limit_price: Optional[float] = None,
    ) -> ExecutionReport:
        """改单。"""
        ...

    def set_prices(self, prices: Mapping[str, float]) -> None:
        """Paper/Simulated 定价；真实 Adapter 可 no-op。"""
        ...
