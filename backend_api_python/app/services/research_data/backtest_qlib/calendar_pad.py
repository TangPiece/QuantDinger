"""Qlib 日历辅助：闭区间回测需要 end 后至少再有一个 calendar bar。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def ensure_calendar_pad(
    cache_path: str | Path,
    *,
    after_date: str | None = None,
    pad_days: int = 1,
) -> bool:
    """确保 ``calendars/day.txt`` 在 ``after_date`` 之后仍有哨兵交易日。

    Qlib ``get_step_time`` 对区间内最后一根 bar 需要 ``calendar[i+1]``。
    哨兵日必须 **严格晚于** backtest ``end_date``，否则会被算进 trade_len。

    Args:
        cache_path: Qlib provider 根目录
        after_date: 回测结束日（含）；缺省则在文件末尾再垫 ``pad_days`` 天
        pad_days: 至少垫几天

    Returns:
        True 表示写入了新日期。
    """
    cal_path = Path(cache_path) / "calendars" / "day.txt"
    if not cal_path.is_file():
        raise FileNotFoundError(cal_path)
    lines = [ln.strip() for ln in cal_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        raise ValueError(f"empty calendar: {cal_path}")

    changed = False
    last = pd.Timestamp(lines[-1])
    target = pd.Timestamp(after_date) if after_date else last
    # 需要严格大于 target 的日期；不足则逐日追加
    need_until = target + pd.Timedelta(days=max(pad_days, 1))
    cursor = last
    while cursor < need_until:
        cursor = cursor + pd.Timedelta(days=1)
        text = cursor.strftime("%Y-%m-%d")
        if text not in lines:
            lines.append(text)
            changed = True
    if changed:
        cal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed
