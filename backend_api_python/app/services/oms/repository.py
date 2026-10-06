"""OMS Repository 薄封装。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .protocol import Order
from .writers import OmsWriter


class OmsRepository:
    def __init__(self, registry: ResearchRegistry, writer: OmsWriter) -> None:
        self._registry = registry
        self._writer = writer

    def get(self, order_id: str) -> Order:
        return self._writer.get_order(order_id)

    def list(self, *, account_id: str = "", status: str = "") -> list[Order]:
        return self._writer.list_orders(account_id=account_id, status=status)
