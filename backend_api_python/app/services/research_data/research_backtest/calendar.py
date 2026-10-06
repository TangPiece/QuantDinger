"""从价格面板推导交易日（不接外部交易所日历 SDK）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence


def _as_date(v: Any) -> date:
    if isinstance(v, date) and not hasattr(v, "hour"):
        return v
    return date.fromisoformat(str(v)[:10])


def trading_calendar_from_bars(
    bars: Sequence[Mapping[str, Any]] | Mapping[tuple[str, date], Mapping[str, Any]],
    *,
    start: date,
    end: date,
) -> list[date]:
    """价格面板出现的日期 ∩ [start, end]，升序去重。"""
    dates: set[date] = set()
    if isinstance(bars, Mapping) and bars and isinstance(next(iter(bars.keys())), tuple):
        for (_inst, d), _bar in bars.items():  # type: ignore[misc]
            dd = _as_date(d)
            if start <= dd <= end:
                dates.add(dd)
    else:
        for row in bars:  # type: ignore[union-attr]
            dd = _as_date(row["trading_date"])
            if start <= dd <= end:
                dates.add(dd)
    return sorted(dates)


def next_trading_day(calendar: Sequence[date], signal_date: date) -> date | None:
    """日历中严格大于 signal_date 的下一交易日。"""
    for d in calendar:
        if d > signal_date:
            return d
    return None
