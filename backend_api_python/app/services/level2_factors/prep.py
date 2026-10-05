"""因子计算用到的清洗和市场判断。只处理已经读入的 Parquet，不读文件。"""
from __future__ import annotations

import pandas as pd

from .timeutil import CONTINUOUS_START, as_time, flag

_SH_STATUS_CODES = {"I", "O", "J", "C"}


def market_of(code: str) -> str:
    """6/9 开头为沪市（含科创板），其余深市。"""
    text = str(code).split(".")[0]
    return "SH" if text[:1] in "69" else "SZ"


def is_equity(code: str) -> bool:
    """A 股：深市 0/3、沪市 6。基金和可转债不进入因子。"""
    text = str(code).split(".")[0]
    return len(text) == 6 and text[:1] in ("0", "3", "6")


def clean_trades(trades: pd.DataFrame, code: str) -> pd.DataFrame:
    """去掉撤单和 09:25 之前的集合竞价，留下连续竞价成交。

    时间先经 ``as_time`` 补成 9 位再比较。原文 ``91500000`` 若直接和 ``092500000``
    做字符串比较，会因为 ``9`` > ``0`` 被误留在连续竞价里。
    """
    if trades is None or len(trades) == 0:
        return trades.copy() if isinstance(trades, pd.DataFrame) else pd.DataFrame()
    frame = trades.copy()
    clock = as_time(frame["时间"])
    price = pd.to_numeric(frame["成交价格"], errors="coerce")
    keep = (price > 0) & (clock >= CONTINUOUS_START)
    if market_of(code) == "SZ":
        # 带空字符的 ``0`` 也是成交，不能只和原始字符串 ``0`` 相等。
        keep = keep & flag(frame["成交代码"]).eq("0")
    return frame.loc[keep].reset_index(drop=True)


def clean_orders(orders: pd.DataFrame, code: str) -> pd.DataFrame:
    """沪市去掉状态行。供需要委托表的口径使用，当前日频因子不依赖它。"""
    if orders is None or len(orders) == 0:
        return orders.copy() if isinstance(orders, pd.DataFrame) else pd.DataFrame()
    frame = orders.copy()
    if market_of(code) == "SH":
        frame = frame[
            frame["委托类型"].astype(str).ne("S")
            & ~frame["委托代码"].astype(str).isin(_SH_STATUS_CODES)
        ]
    return frame.reset_index(drop=True)
