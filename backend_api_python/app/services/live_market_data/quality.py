"""Phase 7B：行情质量标记（dedup / 乱序 / stale / clock_skew）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .protocol import MarketEvent, Quote

FLAG_DEDUP = "dedup"
FLAG_OUT_OF_ORDER = "out_of_order"
FLAG_STALE = "stale"
FLAG_CLOCK_SKEW = "clock_skew"


def _parse_ts(text: str) -> Optional[datetime]:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


class MarketEventQualityTracker:
    """逐 symbol 维护最近 event_id / 时间与序号。"""

    def __init__(
        self,
        *,
        stale_after_sec: float = 120.0,
        max_clock_skew_sec: float = 5.0,
    ) -> None:
        self._stale_after = stale_after_sec
        self._max_skew = max_clock_skew_sec
        self._last_event_id: dict[str, str] = {}
        self._last_event_time: dict[str, datetime] = {}
        self._last_sequence: dict[str, int] = {}

    def annotate(self, event: MarketEvent) -> MarketEvent:
        """返回带 quality_flags 的新 MarketEvent（不修改原对象语义字段）。"""
        flags: list[str] = []
        q = event.quote
        b = event.bar
        symbol = (q.symbol if q else b.symbol if b else "").upper()
        event_id = (q.event_id if q else b.event_id if b else "")
        event_time_s = (q.event_time if q else b.event_time if b else "")
        seq = q.sequence if q and q.sequence is not None else None

        if symbol and event_id and self._last_event_id.get(symbol) == event_id:
            flags.append(FLAG_DEDUP)

        et = _parse_ts(event_time_s)
        now = datetime.now(timezone.utc)
        if et is not None:
            if symbol:
                prev = self._last_event_time.get(symbol)
                if prev is not None and et < prev:
                    flags.append(FLAG_OUT_OF_ORDER)
                self._last_event_time[symbol] = et
            age = (now - et).total_seconds()
            if age > self._stale_after:
                flags.append(FLAG_STALE)
            recv = _parse_ts((q.received_time if q else b.received_time if b else "") or "")
            if recv is not None:
                skew = abs((recv - et).total_seconds())
                if skew > self._max_skew:
                    flags.append(FLAG_CLOCK_SKEW)

        if symbol and seq is not None:
            prev_seq = self._last_sequence.get(symbol)
            if prev_seq is not None and seq <= prev_seq:
                flags.append(FLAG_OUT_OF_ORDER)
            self._last_sequence[symbol] = seq

        if symbol and event_id:
            self._last_event_id[symbol] = event_id

        merged = list(dict.fromkeys([*(event.quality_flags or []), *flags]))
        return event.model_copy(update={"quality_flags": merged})
