"""连续竞价盘口：价差、十档深度、不平衡和委比。

每一行行情大约 3 秒一帧，但时间并不均匀，这里按快照行等权平均，当作时间均值。
集合竞价里买一等于卖一是拟合价，用时间窗口排除，不把连续竞价中的零价差丢掉。
"""
from __future__ import annotations

import math

import pandas as pd

from .timeutil import CONTINUOUS_QUOTE_END, CONTINUOUS_QUOTE_START, as_time

_NAN = float("nan")


def _level_sum(frame: pd.DataFrame, prefix: str) -> pd.Series:
    """十档数量相加。缺档当 0，避免某一档缺失把整行打成空。"""
    total = pd.Series(0.0, index=frame.index)
    seen = False
    for level in range(1, 11):
        column = f"{prefix}{level}"
        if column not in frame.columns:
            continue
        seen = True
        total = total + pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    if not seen:
        return pd.Series(_NAN, index=frame.index)
    return total


def snapshot_factors(snapshot: pd.DataFrame) -> dict[str, float]:
    """连续竞价盘口的时间均值。没有有效快照时各项为 NaN。"""
    empty = {
        "l2_spread": _NAN,
        "l2_depth_bid": _NAN,
        "l2_depth_ask": _NAN,
        "l2_obi": _NAN,
        "l2_order_ratio": _NAN,
    }
    if snapshot is None or len(snapshot) == 0 or "时间" not in snapshot.columns:
        return empty
    frame = snapshot.copy()
    clock = as_time(frame["时间"])
    # 09:30 之后、14:57 之前才是连续竞价报价。9:25 前买一=卖一是集合竞价拟合价。
    frame = frame.loc[(clock >= CONTINUOUS_QUOTE_START) & (clock < CONTINUOUS_QUOTE_END)]
    if len(frame) == 0 or "申买价1" not in frame.columns or "申卖价1" not in frame.columns:
        return empty

    bid = pd.to_numeric(frame["申买价1"], errors="coerce")
    ask = pd.to_numeric(frame["申卖价1"], errors="coerce")
    mid = (bid + ask) / 2.0
    valid = (bid > 0) & (ask > 0) & (mid > 0)
    spread = ((ask - bid) / mid).where(valid)

    depth_bid = _level_sum(frame, "申买量")
    depth_ask = _level_sum(frame, "申卖量")
    depth_sum = depth_bid + depth_ask
    obi = ((depth_bid - depth_ask) / depth_sum).where(depth_sum > 0)

    if "叫买总量" in frame.columns and "叫卖总量" in frame.columns:
        total_bid = pd.to_numeric(frame["叫买总量"], errors="coerce")
        total_ask = pd.to_numeric(frame["叫卖总量"], errors="coerce")
        total = total_bid + total_ask
        ratio = ((total_bid - total_ask) / total).where(total > 0)
    else:
        ratio = pd.Series(_NAN, index=frame.index)

    return {
        "l2_spread": _mean(spread),
        "l2_depth_bid": _mean(depth_bid.where(valid)),
        "l2_depth_ask": _mean(depth_ask.where(valid)),
        "l2_obi": _mean(obi.where(valid)),
        "l2_order_ratio": _mean(ratio.where(valid)),
    }


def _mean(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) == 0:
        return _NAN
    value = float(values.mean())
    return value if math.isfinite(value) else _NAN
