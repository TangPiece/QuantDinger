"""交易日历与 execution_delay 解析（无交易所外部依赖）。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Sequence


class CalendarError(ValueError):
    """日历解析失败。"""


def _parse_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip()[:10])


def _weekday_calendar(start: date, end: date) -> list[date]:
    """工作日日历（周一至周五）。"""
    out: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


# 最小 CN 测试节假日表（可扩展）
_CN_HOLIDAYS: frozenset[date] = frozenset(
    {
        date(2024, 1, 1),
        date(2024, 2, 9),
        date(2024, 2, 12),
        date(2024, 2, 13),
        date(2024, 2, 14),
        date(2024, 2, 15),
        date(2024, 2, 16),
        date(2024, 4, 4),
        date(2024, 4, 5),
        date(2024, 5, 1),
        date(2024, 5, 2),
        date(2024, 5, 3),
        date(2024, 6, 10),
        date(2024, 9, 16),
        date(2024, 9, 17),
        date(2024, 10, 1),
        date(2024, 10, 2),
        date(2024, 10, 3),
        date(2024, 10, 4),
        date(2024, 10, 7),
    }
)


def list_trading_days(
    market_calendar_id: str,
    *,
    start: str | date,
    end: str | date,
    extra_days: Sequence[date] | None = None,
) -> list[date]:
    """列出 [start, end] 内交易日。

    - CN_SSE_SZSE：工作日减去最小节假日表
    - US_NYSE / HK_HKEX / generic：工作日 stub
    - extra_days：测试注入的显式日历（优先）
    """
    s, e = _parse_date(start), _parse_date(end)
    if extra_days is not None:
        return sorted(d for d in extra_days if s <= d <= e)

    weekdays = _weekday_calendar(s, e)
    cal_id = (market_calendar_id or "generic").upper()
    if cal_id in ("CN_SSE_SZSE", "CN"):
        return [d for d in weekdays if d not in _CN_HOLIDAYS]
    return weekdays


def _parse_delay_steps(execution_delay: str) -> int:
    delay = (execution_delay or "T+0").strip().upper()
    if delay in ("T+0", "T0", "0"):
        return 0
    if delay in ("T+1", "T1", "1"):
        return 1
    if delay.startswith("CALENDAR_DAYS:"):
        return int(delay.split(":", 1)[1])
    raise CalendarError(f"unsupported execution_delay: {execution_delay!r}")


def resolve_execution_date(
    signal_date: str | date | datetime,
    execution_delay: str,
    *,
    market_calendar_id: str = "CN_SSE_SZSE",
    calendar: Iterable[date] | None = None,
) -> date:
    """将信号日 + delay 映射为计划成交日。

    - 信号日在日历中：exec = calendar[i + n]
    - 信号日不在日历中：以第一个 >= sig 的交易日为锚点 T，再 + n
    """
    sig = _parse_date(signal_date)
    n = _parse_delay_steps(execution_delay)

    if calendar is not None:
        days = sorted(calendar)
    else:
        days = list_trading_days(
            market_calendar_id,
            start=sig,
            end=sig + timedelta(days=max(60, n * 10 + 30)),
        )
    if not days:
        raise CalendarError(f"empty calendar for {market_calendar_id}")

    if sig in days:
        i = days.index(sig)
    else:
        i = next((k for k, d in enumerate(days) if d >= sig), None)
        if i is None:
            raise CalendarError(f"no trading day on/after {sig}")

    j = i + n
    if j >= len(days):
        raise CalendarError(f"execution date beyond calendar after {sig} delay={execution_delay}")
    return days[j]


def intended_execution_datetime(
    signal_date: str | date | datetime,
    execution_delay: str,
    *,
    market_calendar_id: str = "CN_SSE_SZSE",
    execution_price: str = "open",
    calendar: Iterable[date] | None = None,
) -> datetime:
    """计划成交时刻（naive：open=09:30，close=15:00）。"""
    exec_day = resolve_execution_date(
        signal_date,
        execution_delay,
        market_calendar_id=market_calendar_id,
        calendar=calendar,
    )
    hour, minute = (9, 30) if execution_price == "open" else (15, 0)
    return datetime(exec_day.year, exec_day.month, exec_day.day, hour, minute, 0)
