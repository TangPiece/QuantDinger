"""Phase 7B：Shadow OMS — OrderIntent → ShadowOrder（幂等 client_order_id）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from uuid import uuid4

from app.services.research_data.contracts import OrderIntent

from .protocol import ShadowOrder
from .session import ShadowSession
from .state_machine import assert_shadow_transition


class ShadowOmsError(RuntimeError):
    pass


class ShadowOMS:
    """仅 Shadow 域；不经 BrokerPort。"""

    def __init__(self) -> None:
        self._orders: dict[str, ShadowOrder] = {}
        self._by_client: dict[str, str] = {}

    def submit_intent(
        self,
        intent: OrderIntent,
        *,
        session: ShadowSession,
        strategy_id: str = "",
        risk_approved: bool,
        risk_decision: str = "",
        signal_time: str = "",
        decision_time: str = "",
    ) -> ShadowOrder:
        if not risk_approved:
            raise ShadowOmsError("risk not approved; cannot create ShadowOrder")

        symbol = _symbol_from_intent(intent)
        client_id = _client_order_id(intent)
        if client_id in self._by_client:
            return self._orders[self._by_client[client_id]]

        order_type = "LIMIT" if intent.execution_algorithm == "LIMIT" else "MARKET"
        now = datetime.now(timezone.utc).isoformat()
        order_id = "sho_" + uuid4().hex[:16]
        order = ShadowOrder(
            order_id=order_id,
            strategy_id=strategy_id,
            symbol=symbol,
            side=intent.side,
            quantity=float(intent.quantity),
            order_type=order_type,
            limit_price=intent.limit_price,
            status="SUBMITTED",
            signal_time=signal_time or now,
            decision_time=decision_time or now,
            risk_approved=True,
            risk_decision=risk_decision or "APPROVED",
            created_at=now,
            dataset_hash=session.dataset_hash,
            model_version=session.model_version,
            strategy_version=session.strategy_version,
            client_order_id=client_id,
        )
        assert_shadow_transition(order.status, "ACCEPTED")
        order = order.model_copy(update={"status": "ACCEPTED"})
        self._orders[order_id] = order
        self._by_client[client_id] = order_id
        return order

    def get_order(self, order_id: str) -> ShadowOrder:
        if order_id not in self._orders:
            raise KeyError(order_id)
        return self._orders[order_id]

    def list_orders(self) -> list[ShadowOrder]:
        return list(self._orders.values())

    def update_order(self, order: ShadowOrder) -> None:
        self._orders[order.order_id] = order


def _symbol_from_intent(intent: OrderIntent) -> str:
    key = str(intent.instrument_key or "")
    if ":" in key:
        return key.split(":", 1)[1].upper()
    return key.upper()


def _client_order_id(intent: OrderIntent) -> str:
    tid = (intent.trace_id or intent.signal_id or "").strip()
    if tid:
        return f"cid_{tid}"
    return "cid_" + uuid4().hex[:16]
