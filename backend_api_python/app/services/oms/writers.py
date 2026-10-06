"""Order / Event / Fill / Outbox → Registry + Artifact。"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from app.services.research_data.contracts import (
    OmsFillSummary,
    OmsOrderEventRecord,
    OmsOrderSummary,
    OmsOutboxRecord,
    OrderIntent,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import OmsArtifactStore
from .hash import compute_idempotency_key
from .protocol import (
    ENGINE_VERSION,
    CancelRequest,
    Fill,
    Order,
    OrderEvent,
    OrderVersion,
    OutboxRecord,
    ReplaceRequest,
)


class OmsWriter:
    """持久化 OMS 聚合。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: OmsArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or OmsArtifactStore()

    def get_by_idempotency_for_intent(
        self,
        intent: OrderIntent,
        *,
        account_id: str,
        portfolio_id: str,
        risk_run_id: str = "",
        salt: str = "",
    ) -> Order | None:
        idem = compute_idempotency_key(
            account_id=account_id,
            portfolio_id=portfolio_id,
            instrument_key=intent.instrument_key,
            side=str(intent.side),
            quantity=float(intent.quantity),
            risk_run_id=risk_run_id,
            reason=str(intent.reason or ""),
            salt=salt,
        )
        try:
            summary = self._registry.get_order_by_idempotency(idem)
        except KeyError:
            return None
        return self._order_from_summary(summary)

    def get_order(self, order_id: str) -> Order:
        return self._order_from_summary(self._registry.get_oms_order(order_id))

    def persist_order(
        self,
        order: Order,
        *,
        events: Sequence[OrderEvent] | None = None,
        fills: Sequence[Fill] | None = None,
        outbox: OutboxRecord | None = None,
        version: OrderVersion | None = None,
    ) -> OmsOrderSummary:
        uri = ""
        try:
            uri = self._artifacts.write_order(order)
        except Exception:
            pass
        order = order.model_copy(update={"storage_uri": uri or order.storage_uri})
        summary = OmsOrderSummary(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            broker_order_id=order.broker_order_id,
            account_id=order.account_id,
            portfolio_id=order.portfolio_id,
            risk_run_id=order.risk_run_id,
            policy_hash=order.policy_hash,
            instrument_key=order.instrument_key,
            side=str(order.side),
            order_type=str(order.order_type),
            tif=str(order.tif),
            quantity=float(order.quantity),
            limit_price=order.limit_price,
            filled_quantity=float(order.filled_quantity),
            avg_fill_price=float(order.avg_fill_price),
            status=str(order.status),
            version=int(order.version),
            idempotency_key=order.idempotency_key,
            trading_date=order.trading_date,
            engine_version=order.engine_version or ENGINE_VERSION,
            storage_uri=order.storage_uri,
            created_at=order.created_at,
            metadata=dict(order.metadata or {}),
        )
        self._registry.upsert_oms_order(summary)
        if version is not None:
            self._registry.upsert_oms_order_version(version)
        for ev in events or []:
            self._registry.append_order_event(
                OmsOrderEventRecord(
                    event_id=ev.event_id,
                    order_id=ev.order_id,
                    event_type=ev.event_type,
                    previous_status=ev.previous_status,
                    new_status=ev.new_status,
                    source=ev.source,
                    message=ev.message,
                    payload_json=dict(ev.payload or {}),
                    created_at=ev.created_at,
                )
            )
            try:
                self._artifacts.write_event(ev)
            except Exception:
                pass
        for fill in fills or []:
            self._registry.upsert_fill(
                OmsFillSummary(
                    fill_id=fill.fill_id,
                    order_id=fill.order_id,
                    instrument_key=fill.instrument_key,
                    side=str(fill.side),
                    quantity=float(fill.quantity),
                    price=float(fill.price),
                    fee=float(fill.fee),
                    trading_date=fill.trading_date,
                    created_at=fill.created_at,
                    metadata=dict(fill.metadata or {}),
                )
            )
            try:
                self._artifacts.write_fill(fill)
            except Exception:
                pass
        if outbox is not None:
            self._registry.enqueue_outbox(
                OmsOutboxRecord(
                    outbox_id=outbox.outbox_id,
                    aggregate_type=outbox.aggregate_type,
                    aggregate_id=outbox.aggregate_id,
                    event_type=outbox.event_type,
                    status=str(outbox.status),
                    payload_json=dict(outbox.payload_json or {}),
                    created_at=outbox.created_at,
                    sent_at=outbox.sent_at,
                )
            )
        return summary

    def mark_outbox(self, outbox_id: str, status: str) -> None:
        self._registry.mark_outbox(outbox_id, status)

    def list_outbox(self, limit: int = 100) -> list[OutboxRecord]:
        rows = self._registry.list_outbox(limit=limit)
        return [
            OutboxRecord(
                outbox_id=r.outbox_id,
                aggregate_type=r.aggregate_type,
                aggregate_id=r.aggregate_id,
                event_type=r.event_type,
                status=r.status,  # type: ignore[arg-type]
                payload_json=dict(r.payload_json or {}),
                created_at=r.created_at,
                sent_at=r.sent_at,
            )
            for r in rows
        ]

    def persist_cancel(
        self,
        order: Order,
        *,
        events: Sequence[OrderEvent],
        request: CancelRequest,
    ) -> None:
        self.persist_order(order, events=events)
        self._registry.upsert_cancel_request(request)

    def persist_replace(
        self,
        order: Order,
        *,
        events: Sequence[OrderEvent],
        version: OrderVersion,
        request: ReplaceRequest,
    ) -> None:
        self.persist_order(order, events=events, version=version)
        self._registry.upsert_replace_request(request)

    def list_fills(self, order_id: str) -> list[Fill]:
        rows = self._registry.list_oms_fills(order_id)
        return [
            Fill(
                fill_id=r.fill_id,
                order_id=r.order_id,
                instrument_key=r.instrument_key,
                side=r.side,  # type: ignore[arg-type]
                quantity=float(r.quantity),
                price=float(r.price),
                fee=float(r.fee),
                trading_date=r.trading_date,
                created_at=r.created_at,
                metadata=dict(r.metadata or {}),
            )
            for r in rows
        ]

    def list_events(self, order_id: str) -> list[OrderEvent]:
        rows = self._registry.list_order_events(order_id)
        return [
            OrderEvent(
                event_id=r.event_id,
                order_id=r.order_id,
                event_type=r.event_type,
                previous_status=r.previous_status,
                new_status=r.new_status,
                source=r.source,
                message=r.message,
                payload=dict(r.payload_json or {}),
                created_at=r.created_at,
            )
            for r in rows
        ]

    def list_orders(
        self, *, account_id: str = "", status: str = ""
    ) -> list[Order]:
        rows = self._registry.list_oms_orders(account_id=account_id, status=status)
        return [self._order_from_summary(r) for r in rows]

    @staticmethod
    def _order_from_summary(s: OmsOrderSummary) -> Order:
        return Order(
            order_id=s.order_id,
            client_order_id=s.client_order_id,
            broker_order_id=s.broker_order_id,
            account_id=s.account_id,
            portfolio_id=s.portfolio_id,
            risk_run_id=s.risk_run_id,
            policy_hash=s.policy_hash,
            instrument_key=s.instrument_key,
            side=s.side,  # type: ignore[arg-type]
            order_type=s.order_type,  # type: ignore[arg-type]
            tif=s.tif,  # type: ignore[arg-type]
            quantity=float(s.quantity),
            limit_price=s.limit_price,
            filled_quantity=float(s.filled_quantity),
            avg_fill_price=float(s.avg_fill_price),
            status=s.status,  # type: ignore[arg-type]
            version=int(s.version),
            idempotency_key=s.idempotency_key,
            trading_date=s.trading_date,
            engine_version=s.engine_version or ENGINE_VERSION,
            storage_uri=s.storage_uri,
            created_at=s.created_at,
            metadata=dict(s.metadata or {}),
        )
