"""逐笔成交与撤单：主动净买入、百万大单净流入、撤单率。"""
from __future__ import annotations

import math

import pandas as pd

from .order_agg import big_order_flow
from .prep import clean_trades, market_of

from .names import BIG_ORDER_AMOUNT
from .timeutil import CONTINUOUS_START, as_time, flag

_NAN = float("nan")


def _amounts(trades: pd.DataFrame) -> pd.DataFrame:
    """连续竞价有效成交，并补上金额（元）= 价格 × 数量 / 10000。"""
    if trades is None or len(trades) == 0:
        return pd.DataFrame()
    frame = trades.copy()
    frame["amount"] = (
        pd.to_numeric(frame["成交价格"], errors="coerce")
        * pd.to_numeric(frame["成交数量"], errors="coerce")
        / 10_000.0
    )
    frame["price"] = pd.to_numeric(frame["成交价格"], errors="coerce") / 10_000.0
    return frame


def trade_flow_factors(trades: pd.DataFrame, code: str) -> dict[str, float]:
    """主动净买入率和大单净流入率。大单按委托号聚合，阈值固定 100 万元。"""
    cleaned = clean_trades(trades, code) if len(trades) else trades
    frame = _amounts(cleaned)
    if len(frame) == 0 or frame["amount"].fillna(0).sum() <= 0:
        return {"l2_active_net_buy": _NAN, "l2_big_net_inflow_rate": _NAN}

    side = flag(frame["BS标志"]) if "BS标志" in frame.columns else pd.Series("", index=frame.index)
    buy = float(frame.loc[side.eq("B"), "amount"].sum())
    sell = float(frame.loc[side.eq("S"), "amount"].sum())
    total = float(frame["amount"].sum())
    active = (buy - sell) / total if total > 0 else _NAN

    flow = big_order_flow(frame, BIG_ORDER_AMOUNT)
    big_rate = flow["big_net_inflow"] / total if total > 0 else _NAN
    return {
        "l2_active_net_buy": _finite(active),
        "l2_big_net_inflow_rate": _finite(big_rate),
    }


def cancel_ratio(trades: pd.DataFrame, orders: pd.DataFrame, code: str) -> float:
    """撤单量 / (撤单量 + 成交量)，只统计 09:25 之后。

    深市撤单在成交里，代码 ``C``/``D``；沪市撤单在委托里，类型 ``D``。
    集合竞价撤单不进入，否则开盘撤单会主导全天比率，两边不好横截面比较。
    """
    market = market_of(code)
    trade_qty = _continuous_trade_qty(trades, code)
    if market == "SZ":
        cancel_qty = _sz_cancel_qty(trades)
    else:
        cancel_qty = _sh_cancel_qty(orders)
    denom = trade_qty + cancel_qty
    if denom <= 0:
        return _NAN
    return _finite(cancel_qty / denom)


def _continuous_trade_qty(trades: pd.DataFrame, code: str) -> float:
    if trades is None or len(trades) == 0:
        return 0.0
    cleaned = clean_trades(trades, code)
    if len(cleaned) == 0:
        return 0.0
    return float(pd.to_numeric(cleaned["成交数量"], errors="coerce").fillna(0).sum())


def _sz_cancel_qty(trades: pd.DataFrame) -> float:
    if trades is None or len(trades) == 0 or "成交代码" not in trades.columns:
        return 0.0
    clock = as_time(trades["时间"])
    kind = flag(trades["成交代码"])
    mask = (clock >= CONTINUOUS_START) & kind.isin(["C", "D"])
    return float(pd.to_numeric(trades.loc[mask, "成交数量"], errors="coerce").fillna(0).sum())


def _sh_cancel_qty(orders: pd.DataFrame) -> float:
    if orders is None or len(orders) == 0 or "委托类型" not in orders.columns:
        return 0.0
    clock = as_time(orders["时间"])
    kind = flag(orders["委托类型"])
    mask = (clock >= CONTINUOUS_START) & kind.eq("D")
    return float(pd.to_numeric(orders.loc[mask, "委托数量"], errors="coerce").fillna(0).sum())


def _finite(value: float) -> float:
    value = float(value)
    return value if math.isfinite(value) else _NAN
