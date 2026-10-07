"""Phase 7B：Live MD → Registry + R2。"""

from __future__ import annotations

from app.services.research_data.contracts import LiveMdSessionSummary
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import LiveMdArtifactStore
from .protocol import ENGINE_VERSION, LiveMdSession, MarketEvent


class LiveMdWriter:
    """Session / event batch 索引。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: LiveMdArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or LiveMdArtifactStore()

    def write_session(self, session: LiveMdSession) -> LiveMdSessionSummary:
        summary = LiveMdSessionSummary(
            session_id=session.session_id,
            feed_id=session.feed_id,
            account_id=session.account_id,
            dataset_hash=session.dataset_hash,
            model_version=session.model_version,
            strategy_version=session.strategy_version,
            status=session.status,
            engine_version=ENGINE_VERSION,
            metadata=dict(session.metadata or {}),
        )
        self._registry.upsert_live_md_session(summary)
        return summary

    def write_event_batch(
        self,
        *,
        session: LiveMdSession,
        batch_id: str,
        events: list[MarketEvent],
    ) -> tuple[str, str]:
        uri, cs = self._artifacts.write_event_batch(
            feed_id=session.feed_id,
            batch_id=batch_id,
            events=events,
        )
        return uri, cs
