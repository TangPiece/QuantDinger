"""在日频面板上追加 5/10/20 日均值、标准差和偏度。

滚动窗口含当日，满窗口才出数。pandas rolling 只看当前行及其过去，
``trade_date`` 排好序之后不会用到未来交易日。
"""
from __future__ import annotations

import pandas as pd

from .names import BASE_FACTORS, ROLL_STATS, ROLL_WINDOWS, rollup_name


def add_rollups(frame: pd.DataFrame) -> pd.DataFrame:
    """按股票、交易日排序后计算滚动列。输入至少要有 ``symbol``、``trade_date`` 和基础列。"""
    if frame is None or len(frame) == 0:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    # 丢弃旧索引，滚动结果才能按行号对齐，不受调用方索引重复影响。
    out = frame.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    for base in BASE_FACTORS:
        if base in out.columns:
            out[base] = pd.to_numeric(out[base], errors="coerce")

    # 已有滚动列先丢掉，避免和本次结果重名后再横向拼接出重复列。
    fresh = [rollup_name(base, stat, window) for base in BASE_FACTORS for window in ROLL_WINDOWS for stat in ROLL_STATS]
    out = out.drop(columns=[column for column in fresh if column in out.columns])
    grouped = out.groupby("symbol", sort=False)
    extras: dict[str, pd.Series] = {}
    for base in BASE_FACTORS:
        if base not in out.columns:
            continue
        for window in ROLL_WINDOWS:
            rolled = grouped[base].rolling(window, min_periods=window)
            by_stat = {
                "mean": rolled.mean(),
                "std": rolled.std(),
                "skew": rolled.skew(),
            }
            for stat in ROLL_STATS:
                # reset 掉股票这层索引后，按行号对齐，不按插入顺序把列一块块贴上去。
                extras[rollup_name(base, stat, window)] = by_stat[stat].reset_index(level=0, drop=True)
    return pd.concat([out, pd.DataFrame(extras, index=out.index)], axis=1)
