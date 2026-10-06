"""Broker session / order link / event index → Registry。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from app.services.research_data.contracts import (
    BrokerEventIndexRecord,
    BrokerOrderLinkRecord,
    BrokerSessionSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .hash import derive_session_id
from .protocol import ENGINE_VERSION, BrokerSession
from .raw_store import BrokerRawStore


class BrokerWriter:
    """持久化 6E 索引与 raw。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        raw_store: BrokerRawStore | None = None,
    ) -> None:
        self._registry = registry
        self._raw = raw_store or BrokerRawStore()

    def write_session(self, session: BrokerSession) -> BrokerSessionSummary:
        summary = BrokerSessionSummary(
            session_id=session.session_id,
            broker_id=session.broker_id,
            execution_mode=str(session.execution_mode),
            status=session.status,
            engine_version=session.engine_version or ENGINE_VERSION,
            created_at=session.created_at,
            metadata=dict(session.metadata or {}),
        )
        self._registry.upsert_broker_session(summary)
        return summary

    def link_order(
        self,
        *,
        order_id: str,
        client_order_id: str,
        broker_order_id: str = "",
        broker_id: str = "",
        account_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> BrokerOrderLinkRecord:
        rec = BrokerOrderLinkRecord(
            order_id=order_id,
            client_order_id=client_order_id,
            broker_order_id=broker_order_id,
            broker_id=broker_id,
            account_id=account_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=dict(metadata or {}),
        )
        self._registry.upsert_broker_order_link(rec)
        return rec

    def try_dedup(self, broker_id: str, broker_execution_id: str) -> bool:
        return self._registry.try_record_execution_dedup(
            broker_id, broker_execution_id
        )

    def persist_raw_event(
        self,
        *,
        broker_id: str,
        event_id: str,
        payload: Mapping[str, Any],
    ) -> BrokerEventIndexRecord:
        uri, cs = self._raw.write_event(
            broker_id=broker_id, event_id=event_id, payload=payload
        )
        rec = BrokerEventIndexRecord(
            event_id=event_id,
            broker_id=broker_id,
            received_at=datetime.now(timezone.utc).isoformat(),
            storage_uri=uri,
            checksum=cs,
        )
        self._registry.append_broker_event_index(rec)
        return rec

    def new_session(
        self, broker_id: str, *, execution_mode: str = "PAPER"
    ) -> BrokerSession:
        now = datetime.now(timezone.utc).isoformat()
        sess = BrokerSession(
            session_id=derive_session_id(broker_id, salt=now),
            broker_id=broker_id,
            execution_mode=execution_mode,  # type: ignore[arg-type]
            status="CONNECTED",
            engine_version=ENGINE_VERSION,
            created_at=now,
        )
        self.write_session(sess)
        return sess
