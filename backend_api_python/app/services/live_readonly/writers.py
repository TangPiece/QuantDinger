"""Phase 7A：Live Readonly → Registry + R2。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.contracts import (
    LiveReadonlySessionSummary,
    LiveReadonlySnapshotIndexRecord,
    TradingEnvironmentStateRecord,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import LiveReadonlyArtifactStore
from .protocol import ENGINE_VERSION, LiveReadonlySession
class LiveReadonlyWriter:
    """Session / Snapshot / Environment 索引。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: LiveReadonlyArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or LiveReadonlyArtifactStore()

    def write_session(self, session: LiveReadonlySession) -> LiveReadonlySessionSummary:
        summary = LiveReadonlySessionSummary(
            session_id=session.session_id,
            environment=str(session.environment),
            account_id=session.account_id,
            portfolio_id=session.portfolio_id,
            trading_date=session.trading_date,
            dataset_hash=session.dataset_hash,
            model_version=session.model_version,
            strategy_version=session.strategy_version,
            status=session.status,
            engine_version=ENGINE_VERSION,
            metadata=dict(session.metadata or {}),
        )
        self._registry.upsert_live_readonly_session(summary)
        return summary

    def write_snapshot_index(
        self,
        snapshot: Any,
        *,
        session_id: str = "",
        storage_uri: str = "",
        checksum: str = "",
    ) -> LiveReadonlySnapshotIndexRecord:
        from app.services.reconciliation_service.protocol import BrokerSnapshot

        snap = (
            snapshot
            if isinstance(snapshot, BrokerSnapshot)
            else BrokerSnapshot.model_validate(snapshot)
        )
        rec = LiveReadonlySnapshotIndexRecord(
            snapshot_id=snap.snapshot_id,
            session_id=session_id,
            account_id=snap.account_id,
            captured_at=snap.captured_at or "",
            storage_uri=storage_uri,
            engine_version=ENGINE_VERSION,
            metadata={"checksum": checksum},
        )
        self._registry.upsert_live_readonly_snapshot_index(rec)
        return rec

    def upsert_environment_state(
        self, account_id: str, environment: str, *, metadata: dict | None = None
    ) -> TradingEnvironmentStateRecord:
        from datetime import datetime, timezone

        rec = TradingEnvironmentStateRecord(
            account_id=account_id,
            environment=str(environment),
            updated_at=datetime.now(timezone.utc).isoformat(),
            engine_version=ENGINE_VERSION,
            metadata=dict(metadata or {}),
        )
        self._registry.upsert_trading_environment_state(rec)
        return rec
