"""把 HHMMSSmmm 时间列整理成可以做字符串比较的 9 位文本。"""
from __future__ import annotations

import pandas as pd

# 连续竞价从 09:25 撮合完成开始；盘口均值只取 09:30–14:57，避开集合竞价拟合价。
CONTINUOUS_START = "092500000"
OPEN_AUCTION_END = "093000000"
CONTINUOUS_QUOTE_START = "093000000"
CONTINUOUS_QUOTE_END = "145700000"
OPEN_30_END = "100000000"
TAIL_30_START = "143000000"
AUCTION_ORDER_START = "091500000"


def as_time(series: pd.Series) -> pd.Series:
    """补齐到 9 位。上午小时经常丢前导 0，``93000000`` 要变成 ``093000000``。"""
    text = series.astype(str).str.replace("\x00", "", regex=False).str.strip()
    text = text.str.replace(r"\.0$", "", regex=True)
    return text.str.zfill(9)


def flag(series: pd.Series) -> pd.Series:
    """去掉空字符和空白。沪市空字段有时是字面 NUL，不能直接和 ``B``/``S`` 比较。"""
    return series.astype(str).str.replace("\x00", "", regex=False).str.strip()
