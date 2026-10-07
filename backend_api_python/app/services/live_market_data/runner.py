"""Phase 7B：LiveMarketDataService 主入口（只读 Data；不发单）。"""

from __future__ import annotations

from typing import Any, Iterator, Optional
from uuid import uuid4

from app.services.research_data.registry import ResearchRegistry

from .adapter import quote_from_alpaca, to_market_event_quote
from .artifact_store import LiveMdArtifactStore
from .gate import require_production_ready
from .hash import derive_event_batch_id, derive_md_session_id
from .protocol import LiveMdSession, MarketEvent
from .quality import MarketEventQualityTracker
from .session import assert_session_locked, merge_session_update, open_md_session
from .stream import LiveMdStreamStub
from .transport import AlpacaLiveMdTransport, FakeLiveMdTransport
from .writers import LiveMdWriter


class LiveMarketDataError(RuntimeError):
    """Live MD 服务错误。"""


class LiveMarketDataService:
    """真实/Fake 行情编排；connect 需 PRODUCTION_READY（真实 transport）。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        transport: Any | None = None,
        artifact_store: LiveMdArtifactStore | None = None,
        use_fake: bool = True,
    ) -> None:
        self._store = store
        self._registry = registry
        self._transport = transport
        self._use_fake = use_fake
        self._writer = LiveMdWriter(registry, artifact_store=artifact_store)
        self._session: LiveMdSession | None = None
        self._quality = MarketEventQualityTracker()
        self._stream = LiveMdStreamStub(on_reconnect=self._on_stream_reconnect)
        self._batch_seq = 0
        self._connected = False

    def _on_stream_reconnect(self) -> None:
        # 重连 hook：仅记录 metadata，不触网发单
        if self._session is not None:
            self._session = merge_session_update(
                self._session,
                {"metadata": {**(self._session.metadata or {}), "stream_reconnected": True}},
            )

    def connect(self) -> None:
        if self._transport is None:
            if self._use_fake:
                self._transport = FakeLiveMdTransport()
            else:
                require_production_ready(self._registry)
                self._transport = AlpacaLiveMdTransport()
        self._connected = True
        self._stream.connect()

    def disconnect(self) -> None:
        self._connected = False
        self._stream.disconnect()

    def health(self) -> dict[str, Any]:
        return {
            "connected": self._connected,
            "fake": isinstance(self._transport, FakeLiveMdTransport),
            "session_id": self._session.session_id if self._session else "",
        }

    def start_session(
        self,
        *,
        feed_id: str = "default",
        account_id: str = "",
        dataset_hash: str,
        model_version: str,
        strategy_version: str,
    ) -> LiveMdSession:
        session = open_md_session(
            feed_id=feed_id,
            account_id=account_id,
            dataset_hash=dataset_hash,
            model_version=model_version,
            strategy_version=strategy_version,
            salt=str(uuid4())[:8],
        )
        self._writer.write_session(session)
        self._session = session
        return session

    def lock_check(self, *, dataset_hash: str) -> None:
        if self._session is None:
            raise LiveMarketDataError("no open session")
        assert_session_locked(self._session, dataset_hash=dataset_hash)

    def get_quote(self, symbol: str) -> MarketEvent:
        self._ensure_transport()
        raw = self._transport.get_latest_quote(symbol)
        quote = quote_from_alpaca(symbol, raw)
        ev = to_market_event_quote(quote)
        return self._quality.annotate(ev)

    def get_bars(self, symbol: str, **kwargs: Any) -> dict[str, Any]:
        self._ensure_transport()
        return self._transport.get_bars(symbol, **kwargs)

    def poll_events(self, symbols: list[str]) -> list[MarketEvent]:
        """拉取一批 quote 事件（Fake/真实 GET）。"""
        events = [self.get_quote(s) for s in symbols]
        self._persist_batch(events)
        return events

    def _persist_batch(self, events: list[MarketEvent]) -> None:
        if not self._session or not events:
            return
        self._batch_seq += 1
        batch_id = derive_event_batch_id(
            session_id=self._session.session_id, seq=self._batch_seq
        )
        self._writer.write_event_batch(
            session=self._session, batch_id=batch_id, events=events
        )

    def _ensure_transport(self) -> None:
        if self._transport is None or not self._connected:
            raise LiveMarketDataError("not connected")
