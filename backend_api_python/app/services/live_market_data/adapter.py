"""Phase 7B：Alpaca vendor payload → Canonical MarketEvent。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from .protocol import Bar, MarketEvent, Quote


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def quote_from_alpaca(symbol: str, raw: Mapping[str, Any], *, source: str = "alpaca") -> Quote:
    """解析 Alpaca latest quote 响应。"""
    q = raw.get("quote") if isinstance(raw.get("quote"), dict) else raw
    return Quote(
        symbol=str(symbol).upper(),
        exchange="US",
        bid=_float(q.get("bp")),
        ask=_float(q.get("ap")),
        bid_size=_float(q.get("bs")),
        ask_size=_float(q.get("as")),
        last=_float(q.get("p") or q.get("last")),
        volume=_float(q.get("v")),
        event_time=str(q.get("t") or q.get("timestamp") or ""),
        received_time=_now_iso(),
        source=source,
        event_id=str(q.get("i") or uuid4().hex[:16]),
    )


def bar_from_alpaca(symbol: str, raw: Mapping[str, Any], *, source: str = "alpaca") -> Bar:
    """解析单条 Alpaca bar。"""
    return Bar(
        symbol=str(symbol).upper(),
        exchange="US",
        open=_float(raw.get("o")) or 0.0,
        high=_float(raw.get("h")) or 0.0,
        low=_float(raw.get("l")) or 0.0,
        close=_float(raw.get("c")) or 0.0,
        volume=_float(raw.get("v")) or 0.0,
        vwap=_float(raw.get("vw")),
        event_time=str(raw.get("t") or ""),
        received_time=_now_iso(),
        source=source,
        event_id=str(raw.get("i") or uuid4().hex[:16]),
        timeframe=str(raw.get("timeframe") or "1Min"),
    )


def to_market_event_quote(quote: Quote, *, quality_flags: list[str] | None = None) -> MarketEvent:
    return MarketEvent(
        kind="quote",
        quote=quote,
        quality_flags=list(quality_flags or []),
    )


def to_market_event_bar(bar: Bar, *, quality_flags: list[str] | None = None) -> MarketEvent:
    return MarketEvent(
        kind="bar",
        bar=bar,
        quality_flags=list(quality_flags or []),
    )


def _float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
