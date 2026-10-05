"""日频 CN 信号时间语义（Phase 2E 研究约定；Phase 3 再换交易日历）。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# A 股常用会话时区
_CN_TZ = ZoneInfo("Asia/Shanghai")


def _as_date(trading_date: str | date) -> date:
    if isinstance(trading_date, date) and not isinstance(trading_date, datetime):
        return trading_date
    text = str(trading_date)[:10]
    return date.fromisoformat(text)


def resolve_signal_times(
    trading_date: str | date,
) -> tuple[datetime, datetime, datetime]:
    """返回 (signal_time, knowledge_time, execution_time)，均为 UTC aware。

    约定：
    - signal_time / knowledge_time = trading_date 15:00 Asia/Shanghai
    - execution_time = 下一自然日 09:30 Asia/Shanghai（非交易日历；回测细化留给 Phase 3）
    """
    d = _as_date(trading_date)
    local_close = datetime(d.year, d.month, d.day, 15, 0, 0, tzinfo=_CN_TZ)
    next_d = d + timedelta(days=1)
    local_open = datetime(
        next_d.year, next_d.month, next_d.day, 9, 30, 0, tzinfo=_CN_TZ
    )
    signal_time = local_close.astimezone(timezone.utc)
    knowledge_time = signal_time
    execution_time = local_open.astimezone(timezone.utc)
    return signal_time, knowledge_time, execution_time
