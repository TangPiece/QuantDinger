"""MarketDataProvider：PAPER/SHADOW 只经 Canonical / DataQuery，禁止 Runtime 直打交易所 HTTP。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Protocol, Sequence

from .session import MarketSchedule


class MarketDataProvider(Protocol):
    """统一行情入口。"""

    def bars(
        self,
        instruments: Sequence[str],
        start: date,
        end: date,
        *,
        as_of: date | datetime | None = None,
    ) -> list[dict[str, Any]]: ...

    def latest_session(self, market: str) -> date: ...


class InjectedMarketDataProvider:
    """Golden / 测试注入 price_bars。"""

    def __init__(
        self,
        price_bars: Sequence[dict[str, Any]] | None = None,
        *,
        schedule: MarketSchedule | None = None,
        market: str = "CN_A",
    ) -> None:
        self._bars = [dict(r) for r in (price_bars or [])]
        self._schedule = schedule or MarketSchedule()
        self._market = market

    def bars(
        self,
        instruments: Sequence[str],
        start: date,
        end: date,
        *,
        as_of: date | datetime | None = None,
    ) -> list[dict[str, Any]]:
        keys = {str(x) for x in instruments} if instruments else set()
        as_of_d = _as_date(as_of) if as_of is not None else end
        out: list[dict[str, Any]] = []
        for r in self._bars:
            inst = str(r.get("instrument_key") or r.get("instrument") or "")
            if keys and inst not in keys:
                continue
            td = str(r.get("trading_date") or r.get("datetime") or "")[:10]
            if not td:
                continue
            d = date.fromisoformat(td)
            if d < start or d > end or d > as_of_d:
                continue
            out.append(dict(r))
        return out

    def latest_session(self, market: str) -> date:
        if self._bars:
            dates = [
                date.fromisoformat(str(r.get("trading_date") or "")[:10])
                for r in self._bars
                if r.get("trading_date")
            ]
            if dates:
                return max(dates)
        return self._schedule.latest_session_date(market or self._market)


class HistoricalMarketDataProvider:
    """经 DataQuery.market 读 Canonical 日线。"""

    def __init__(self, query: Any, *, exchange: str = "CN") -> None:
        self._query = query
        self._exchange = exchange
        self._schedule = MarketSchedule()

    def bars(
        self,
        instruments: Sequence[str],
        start: date,
        end: date,
        *,
        as_of: date | datetime | None = None,
    ) -> list[dict[str, Any]]:
        end_eff = _as_date(as_of) if as_of is not None else end
        if end_eff < start:
            return []
        df = self._query.market(
            list(instruments),
            start,
            end_eff,
            frequency="1d",
            exchange=self._exchange,
        )
        if df is None or getattr(df, "empty", True):
            return []
        return df.to_dict(orient="records")

    def latest_session(self, market: str) -> date:
        return self._schedule.latest_session_date(market)


class PaperAsOfMarketDataProvider:
    """PAPER/SHADOW 默认：Canonical 截至 latest completed session 切片。"""

    def __init__(
        self,
        query: Any | None = None,
        *,
        schedule: MarketSchedule | None = None,
        market: str = "CN_A",
        exchange: str = "CN",
        injected: Sequence[dict[str, Any]] | None = None,
        lookback_days: int = 60,
    ) -> None:
        self._schedule = schedule or MarketSchedule()
        self._market = market
        self._injected = (
            InjectedMarketDataProvider(injected, schedule=self._schedule, market=market)
            if injected is not None
            else None
        )
        self._hist = (
            HistoricalMarketDataProvider(query, exchange=exchange) if query is not None else None
        )
        self._lookback = lookback_days

    def bars(
        self,
        instruments: Sequence[str],
        start: date,
        end: date,
        *,
        as_of: date | datetime | None = None,
    ) -> list[dict[str, Any]]:
        as_of_d = _as_date(as_of) if as_of is not None else self.latest_session(self._market)
        end_eff = min(end, as_of_d)
        if self._injected is not None:
            return self._injected.bars(instruments, start, end_eff, as_of=as_of_d)
        if self._hist is None:
            return []
        return self._hist.bars(instruments, start, end_eff, as_of=as_of_d)

    def latest_session(self, market: str) -> date:
        if self._injected is not None:
            return self._injected.latest_session(market)
        return self._schedule.latest_session_date(market or self._market)

    def default_window(self, *, as_of: date | None = None) -> tuple[date, date]:
        end = as_of or self.latest_session(self._market)
        start = end - timedelta(days=self._lookback)
        return start, end


def _as_date(v: date | datetime | None) -> date:
    if v is None:
        return date.today()
    if isinstance(v, datetime):
        return v.date()
    return v
