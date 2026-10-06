"""DataQuery → 按日 MarketBar（区间预取 + 单日 trading_status）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Sequence

import pandas as pd

from app.services.research_data.backtest.execution.models import MarketBar
from app.services.research_data.contracts import PricePolicy
from app.services.research_data.data_query import DataQuery


@dataclass
class MarketPanel:
    """回测窗口行情面板：日历 + 按日 MarketBar。"""

    calendar: list[date]
    bars_by_date: dict[str, dict[str, MarketBar]] = field(default_factory=dict)

    def bars_for(self, trading_date: str | date) -> dict[str, MarketBar]:
        key = trading_date.isoformat() if isinstance(trading_date, date) else str(trading_date)[:10]
        return dict(self.bars_by_date.get(key) or {})


def _to_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    return pd.Timestamp(value).date()


def load_market_panel(
    query: DataQuery,
    *,
    instrument_keys: Sequence[str],
    start: date,
    end: date,
    price_policy: PricePolicy | None = None,
    exchange: str = "CN",
    fetch_trading_status: bool = True,
) -> MarketPanel:
    """一次预取 market 区间，再按日拼装 MarketBar（status 按日查）。"""
    keys = list(instrument_keys)
    if not keys:
        return MarketPanel(calendar=[])

    market = query.market(
        keys,
        start,
        end,
        frequency="1d",
        price_policy=price_policy,
        exchange=exchange,
    )
    if market.empty:
        return MarketPanel(calendar=[])

    market = market.copy()
    market["trading_date"] = pd.to_datetime(market["trading_date"]).dt.date
    calendar = sorted(set(market["trading_date"].tolist()))

    bars_by_date: dict[str, dict[str, MarketBar]] = {}
    for day in calendar:
        day_df = market[market["trading_date"] == day]
        status_map: dict[str, dict] = {}
        if fetch_trading_status:
            try:
                st = query.trading_status(keys, day, exchange=exchange)
            except Exception:
                st = pd.DataFrame()
            if st is not None and not st.empty:
                st = st.copy()
                st["trading_date"] = pd.to_datetime(st["trading_date"]).dt.date
                for _, row in st.iterrows():
                    status_map[str(row["instrument_key"])] = row.to_dict()

        day_bars: dict[str, MarketBar] = {}
        for _, row in day_df.iterrows():
            ik = str(row["instrument_key"])
            st_row = status_map.get(ik, {})
            day_bars[ik] = MarketBar(
                instrument_key=ik,
                trading_date=day.isoformat(),
                open=_f(row.get("open")),
                high=_f(row.get("high")),
                low=_f(row.get("low")),
                close=_f(row.get("close")),
                vwap=_f(row.get("vwap")),
                volume=_f(row.get("volume")),
                is_suspended=bool(st_row.get("is_suspended", False)),
                is_limit_up=bool(st_row.get("is_limit_up", False)),
                is_limit_down=bool(st_row.get("is_limit_down", False)),
                upper_limit=_f(st_row.get("upper_limit")),
                lower_limit=_f(st_row.get("lower_limit")),
            )
        bars_by_date[day.isoformat()] = day_bars

    return MarketPanel(calendar=calendar, bars_by_date=bars_by_date)


def market_panel_from_bars(
    bars_by_date: Mapping[str, Mapping[str, MarketBar]],
) -> MarketPanel:
    """测试注入：从内存 bars 构建面板。"""
    calendar = sorted(date.fromisoformat(k[:10]) for k in bars_by_date.keys())
    normalized = {k[:10]: dict(v) for k, v in bars_by_date.items()}
    return MarketPanel(calendar=calendar, bars_by_date=normalized)


def _f(value) -> float | None:
    if value is None:
        return None
    try:
        import math

        f = float(value)
        if math.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None
