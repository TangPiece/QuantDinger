"""Phase 7B：实现 production_runtime.MarketDataProvider（经 Live MD）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Sequence

from .adapter import bar_from_alpaca, quote_from_alpaca
from .protocol import Bar
from .transport import FakeLiveMdTransport


class LiveMarketDataProvider:
    """将 Alpaca/Fake bars 转为 production_runtime 期望的 dict 行。"""

    def __init__(self, transport: Any | None = None) -> None:
        self._transport = transport or FakeLiveMdTransport()

    def bars(
        self,
        instruments: Sequence[str],
        start: date,
        end: date,
        *,
        as_of: date | datetime | None = None,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for inst in instruments:
            sym = _symbol_from_instrument(inst)
            raw = self._transport.get_bars(sym, limit=500)
            bars = raw.get("bars") if isinstance(raw, dict) else raw
            if not isinstance(bars, list):
                continue
            for row in bars:
                bar: Bar = bar_from_alpaca(sym, row, source="live_md")
                td = (bar.event_time or "")[:10]
                if not td:
                    continue
                try:
                    d = date.fromisoformat(td)
                except ValueError:
                    continue
                if d < start or d > end:
                    continue
                out.append(
                    {
                        "instrument_key": str(inst),
                        "trading_date": td,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                )
        return out

    def latest_session(self, market: str) -> date:
        _ = market
        return date.today()

    def get_quote_dict(self, symbol: str) -> dict[str, Any]:
        """辅助：拉最新 quote 并返回 Quote model_dump。"""
        raw = self._transport.get_latest_quote(symbol)
        q = quote_from_alpaca(symbol, raw)
        return q.model_dump(mode="json")


def _symbol_from_instrument(instrument_key: str) -> str:
    text = str(instrument_key or "")
    if ":" in text:
        return text.split(":", 1)[1]
    return text
