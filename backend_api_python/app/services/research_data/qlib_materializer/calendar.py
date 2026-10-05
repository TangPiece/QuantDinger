"""研究日历：来自 DataQuery market 的 trading_date，非 Qlib 默认日历。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence

import pandas as pd


def calendar_from_market(market: pd.DataFrame) -> list[date]:
    """提取去重有序交易日。"""
    if market.empty or "trading_date" not in market.columns:
        return []
    dates = pd.to_datetime(market["trading_date"]).dt.date
    return sorted(set(dates.tolist()))


def write_calendar_day_txt(path: Path, calendar: Sequence[date]) -> None:
    """写出 Qlib calendars/day.txt。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [d.isoformat() for d in calendar]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def read_calendar_day_txt(path: Path) -> list[date]:
    """读回 day.txt。"""
    if not path.is_file():
        return []
    out: list[date] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            out.append(date.fromisoformat(text))
    return out
