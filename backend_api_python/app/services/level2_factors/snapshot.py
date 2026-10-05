"""连续竞价盘口：价差、十档深度、不平衡、订单流不平衡和委比。

每一行行情大约 3 秒一帧，但时间并不均匀，这里按快照行等权平均，当作时间均值。
集合竞价里买一等于卖一是拟合价，用时间窗口排除，不把连续竞价中的零价差丢掉。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .timeutil import CONTINUOUS_QUOTE_END, CONTINUOUS_QUOTE_START, as_time

_NAN = float("nan")
# 十档里越靠近成交价权重越大：第 k 档权重 (11-k)，归一化后合计为 1。
_OFI_LEVELS = 10
_OFI_WEIGHTS = np.arange(_OFI_LEVELS, 0, -1, dtype=float)
_OFI_WEIGHTS = _OFI_WEIGHTS / _OFI_WEIGHTS.sum()
# 行情大约 3 秒一帧。超过 1 分钟的空洞（午休、停牌）不把两边盘口相减。
_OFI_MAX_GAP_SECONDS = 60.0


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
        "l2_ofi": _NAN,
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
        "l2_ofi": _ofi(frame),
        "l2_order_ratio": _mean(ratio.where(valid)),
    }


def _mean(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) == 0:
        return _NAN
    value = float(values.mean())
    return value if math.isfinite(value) else _NAN


def _ofi(frame: pd.DataFrame) -> float:
    """Cont 式十档快照 OFI，再除以这些快照的平均十档深度。

    每一档用相邻两帧的价格和数量：价涨只记新挂量，价跌只记旧挂量消失，价不变记数量差。
    卖盘符号相反。缺档或价格不是正数的那一档贡献 0，不把整帧丢掉。
    """
    if "申买价1" not in frame.columns or "申卖价1" not in frame.columns:
        return _NAN
    seconds = _clock_seconds(as_time(frame["时间"]))
    ordered = frame.assign(_sec=seconds.to_numpy())
    ordered = ordered.loc[np.isfinite(ordered["_sec"].to_numpy())]
    ordered = ordered.sort_values("_sec", kind="mergesort").drop_duplicates("_sec", keep="last")
    if len(ordered) < 2:
        return _NAN

    gap = ordered["_sec"].diff().to_numpy()
    pair_ok = (gap > 0) & (gap <= _OFI_MAX_GAP_SECONDS)
    best_bid = _numeric(ordered, "申买价1")
    best_ask = _numeric(ordered, "申卖价1")
    quote_ok = (best_bid > 0) & (best_ask > 0) & np.isfinite(best_bid) & np.isfinite(best_ask)
    previous_quote = np.zeros(len(ordered), dtype=bool)
    previous_quote[1:] = quote_ok[:-1]
    pair_ok = pair_ok & quote_ok & previous_quote

    ofi = np.zeros(len(ordered), dtype=float)
    for level, weight in enumerate(_OFI_WEIGHTS, start=1):
        ofi += weight * (
            _bid_delta(_numeric(ordered, f"申买价{level}"), _numeric(ordered, f"申买量{level}"))
            + _ask_delta(_numeric(ordered, f"申卖价{level}"), _numeric(ordered, f"申卖量{level}"))
        )
    ofi = np.where(pair_ok, ofi, np.nan)
    if not np.isfinite(ofi).any():
        return _NAN
    depth = _book_depth(ordered)
    scale = float(np.mean(depth[np.isfinite(ofi)]))
    if not math.isfinite(scale) or scale <= 0:
        return _NAN
    return float(np.nansum(ofi) / scale)


def _clock_seconds(clock: pd.Series) -> pd.Series:
    """9 位 HHMMSSmmm 换成当日秒数，坏值是 NaN。"""
    digits = clock.astype(str).str.replace(r"\D", "", regex=True).str.slice(0, 9)
    hours = pd.to_numeric(digits.str.slice(0, 2), errors="coerce")
    minutes = pd.to_numeric(digits.str.slice(2, 4), errors="coerce")
    seconds = pd.to_numeric(digits.str.slice(4, 6), errors="coerce")
    millis = pd.to_numeric(digits.str.slice(6, 9), errors="coerce")
    return hours * 3600.0 + minutes * 60.0 + seconds + millis / 1000.0


def _numeric(frame: pd.DataFrame, column: str) -> np.ndarray:
    """缺列当成全 NaN，让这一档不参与 OFI。"""
    if column not in frame.columns:
        return np.full(len(frame), np.nan)
    return pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)


def _bid_delta(price: np.ndarray, size: np.ndarray) -> np.ndarray:
    """买档：价升记新量，价降记旧量的消失，价平记数量差。"""
    return _queue_delta(price, size, price_up_is_positive=True)


def _ask_delta(price: np.ndarray, size: np.ndarray) -> np.ndarray:
    """卖档符号与买档相反：卖价下移或卖量增加是卖压。"""
    return -_queue_delta(price, size, price_up_is_positive=False)


def _queue_delta(price: np.ndarray, size: np.ndarray, *, price_up_is_positive: bool) -> np.ndarray:
    """按价格升降把相邻两帧的挂单量变成一档贡献。第一帧没有前值，贡献 0。"""
    previous_price = np.empty_like(price)
    previous_size = np.empty_like(size)
    previous_price[0] = np.nan
    previous_size[0] = np.nan
    previous_price[1:] = price[:-1]
    previous_size[1:] = size[:-1]
    quantity = np.where(np.isfinite(size), size, 0.0)
    previous_quantity = np.where(np.isfinite(previous_size), previous_size, 0.0)
    higher_or_equal = price >= previous_price
    lower_or_equal = price <= previous_price
    if price_up_is_positive:
        delta = np.where(higher_or_equal, quantity, 0.0) - np.where(lower_or_equal, previous_quantity, 0.0)
    else:
        # 卖价下降才算新卖压，所以比较方向和买档对调。
        delta = np.where(lower_or_equal, quantity, 0.0) - np.where(higher_or_equal, previous_quantity, 0.0)
    valid = (price > 0) & (previous_price > 0) & np.isfinite(price) & np.isfinite(previous_price)
    delta = np.where(valid, delta, 0.0)
    delta[0] = 0.0
    return delta


def _book_depth(frame: pd.DataFrame) -> np.ndarray:
    """十档买卖量之和，用来把股数 OFI 收成无量纲。缺档当 0。"""
    total = np.zeros(len(frame), dtype=float)
    for level in range(1, _OFI_LEVELS + 1):
        for prefix in ("申买量", "申卖量"):
            total += np.nan_to_num(_numeric(frame, f"{prefix}{level}"), nan=0.0)
    return total
