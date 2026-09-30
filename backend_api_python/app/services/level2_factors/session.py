"""集合竞价、隔夜/日内收益，以及 1 分钟已实现波动和偏度。"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .prep import clean_trades, market_of

from .names import PRICE_SCALE
from .timeutil import (
    AUCTION_ORDER_START,
    CONTINUOUS_QUOTE_END,
    CONTINUOUS_QUOTE_START,
    CONTINUOUS_START,
    OPEN_30_END,
    OPEN_AUCTION_END,
    TAIL_30_START,
    as_time,
    flag,
)

_NAN = float("nan")
_SH_STATUS = {"I", "O", "J", "C"}


def auction_amount(trades: pd.DataFrame) -> float:
    """9:30 前、价格大于 0 的成交额（元），含 09:25 撮合打印。没有成交表时为 NaN。"""
    if trades is None or len(trades) == 0 or "成交价格" not in trades.columns:
        return _NAN
    clock = as_time(trades["时间"])
    price = pd.to_numeric(trades["成交价格"], errors="coerce")
    qty = pd.to_numeric(trades["成交数量"], errors="coerce")
    mask = (clock < OPEN_AUCTION_END) & (price > 0)
    if "成交代码" in trades.columns:
        # 深市竞价撤单价格为 0，这里再挡一层，避免把撤单当成成交。
        mask = mask & ~flag(trades["成交代码"]).isin(["C", "D"])
    amount = (price * qty / PRICE_SCALE).where(mask)
    return _finite(float(amount.sum(skipna=True)))


def auction_imbalance(orders: pd.DataFrame, trades: pd.DataFrame, code: str) -> float:
    """9:15–9:25 未撤完的有效委托：(买量 - 卖量) / (买量 + 卖量)。

    结束时刻是 09:25。09:25 之后挂上的单子属于连续竞价，不进竞价不平衡。
    同一委托号只扣掉撤单量，剩余大于 0 的部分仍算有效申报。
    """
    if orders is None or len(orders) == 0 or "委托代码" not in orders.columns:
        return _NAN
    clock = as_time(orders["时间"])
    window = orders.loc[(clock >= AUCTION_ORDER_START) & (clock < CONTINUOUS_START)].copy()
    if len(window) == 0:
        return _NAN

    if market_of(code) == "SH" and "委托类型" in window.columns:
        # 沪市状态行（I/O/J/C）和撤单行本身不是可成交委托。
        kind = flag(window["委托类型"])
        window = window.loc[kind.eq("A")]
    if len(window) == 0:
        return _NAN

    side = flag(window["委托代码"])
    side = side.where(~side.isin(_SH_STATUS))
    buy, sell = _remaining_auction_qty(window, side, _cancelled_quantities(orders, trades, code))
    denom = buy + sell
    if denom <= 0:
        return _NAN
    return _finite((buy - sell) / denom)


def _remaining_auction_qty(window: pd.DataFrame, side: pd.Series, cancelled: dict[str, float]) -> tuple[float, float]:
    """按委托号汇总申报量后再扣撤单量。同一号两边都有时，撤单只从数量更大的一边扣。"""
    if "交易所委托号" in window.columns:
        order_ids = window["交易所委托号"].map(_order_key)
    else:
        order_ids = pd.Series("", index=window.index)
    qty = pd.to_numeric(window["委托数量"], errors="coerce").fillna(0.0)
    frame = pd.DataFrame({"id": order_ids.to_numpy(), "side": side.to_numpy(), "qty": qty.to_numpy()})
    frame = frame.loc[frame["side"].isin(["B", "S"])]
    if len(frame) == 0:
        return 0.0, 0.0
    totals = frame.groupby(["id", "side"], sort=False)["qty"].sum().reset_index()
    # 撤单量只扣一次。先扣数量更大的一边，剩下的再扣另一边。
    leftover = dict(cancelled)
    buy = 0.0
    sell = 0.0
    ordered = totals.sort_values("qty", ascending=False)
    for row in ordered.itertuples(index=False):
        taken = min(float(row.qty), float(leftover.get(row.id, 0.0)))
        leftover[row.id] = float(leftover.get(row.id, 0.0)) - taken
        remaining = float(row.qty) - taken
        if remaining <= 0:
            continue
        if row.side == "B":
            buy += remaining
        else:
            sell += remaining
    return buy, sell


def _cancelled_quantities(orders: pd.DataFrame, trades: pd.DataFrame, code: str) -> dict[str, float]:
    """09:25 前各委托号的撤单量。沪市看委托 D，深市看成交 C/D 的叫买/叫卖序号。"""
    totals: dict[str, float] = {}
    if market_of(code) == "SH":
        if orders is None or len(orders) == 0 or "委托类型" not in orders.columns or "交易所委托号" not in orders.columns:
            return totals
        clock = as_time(orders["时间"])
        rows = orders.loc[(clock < CONTINUOUS_START) & flag(orders["委托类型"]).eq("D")]
        amounts = rows["委托数量"] if "委托数量" in rows.columns else None
        _add_cancel_qty(totals, rows["交易所委托号"], amounts)
        return totals

    if trades is None or len(trades) == 0 or "成交代码" not in trades.columns:
        return totals
    clock = as_time(trades["时间"])
    rows = trades.loc[(clock < CONTINUOUS_START) & flag(trades["成交代码"]).isin(["C", "D"])]
    amounts = rows["成交数量"] if "成交数量" in rows.columns else pd.Series(0.0, index=rows.index)
    for column in ("叫买序号", "叫卖序号"):
        if column in rows.columns:
            _add_cancel_qty(totals, rows[column], amounts)
    return totals


def _add_cancel_qty(totals: dict[str, float], ids: pd.Series, qty: pd.Series | None) -> None:
    """把有效委托号上的撤单量累加。0 和空号跳过，避免对到无关申报。"""
    if qty is None:
        return
    amounts = pd.to_numeric(qty, errors="coerce").fillna(0.0)
    for order_id, amount in zip(ids.map(_order_key), amounts):
        if not order_id or amount <= 0:
            continue
        totals[order_id] = totals.get(order_id, 0.0) + float(amount)


def _order_key(value: object) -> str:
    """委托号规范化。0、空和缺失不算有效号。"""
    text = str(value).replace("\x00", "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text in {"", "0", "nan", "None", "NaN", "<NA>"}:
        return ""
    return text


def session_returns(snapshot: pd.DataFrame, trades: pd.DataFrame, code: str) -> dict[str, float]:
    """隔夜、开盘 30 分钟、尾盘 30 分钟、日内收益。价格优先用行情官方开收和前收。"""
    cleaned = clean_trades(trades, code) if trades is not None and len(trades) else pd.DataFrame()
    priced = _with_price(cleaned)
    official = _official_prices(snapshot)
    open_px = official["open"]
    close_px = official["close"]
    prev_px = official["prev_close"]
    if not math.isfinite(open_px):
        open_px = _first_price(priced, CONTINUOUS_QUOTE_START)
    if not math.isfinite(close_px):
        close_px = _last_price(priced, CONTINUOUS_QUOTE_START)

    open_30_end = _last_price_between(priced, CONTINUOUS_QUOTE_START, OPEN_30_END)
    tail_start = _first_price(priced, TAIL_30_START)
    tail_end = _last_price(priced, TAIL_30_START)
    return {
        "l2_ret_overnight": _ratio(open_px, prev_px),
        "l2_ret_open_30": _ratio(open_30_end, open_px),
        "l2_ret_tail_30": _ratio(tail_end, tail_start),
        "l2_ret_intraday": _ratio(close_px, open_px),
    }


def realized_moments(trades: pd.DataFrame, code: str) -> dict[str, float]:
    """连续竞价 1 分钟末价的对数收益：``sqrt(Σ r^2)`` 与 ``Σ r^3 / (Σ r^2)^{3/2}``。

    只连接相邻分钟。午休和缺分钟会被跳过，避免把 11:30 到 13:00 当成一分钟收益。
    """
    empty = {"l2_rv": _NAN, "l2_rskew": _NAN}
    if trades is None or len(trades) == 0:
        return empty
    cleaned = clean_trades(trades, code)
    priced = _with_price(cleaned)
    if len(priced) == 0:
        return empty
    clock = as_time(priced["时间"])
    priced = priced.loc[(clock >= CONTINUOUS_QUOTE_START) & (clock < CONTINUOUS_QUOTE_END)].copy()
    if len(priced) == 0:
        return empty
    priced["_minute"] = clock.loc[priced.index].str.slice(0, 4)
    last = priced.groupby("_minute", sort=True)["price"].last()
    minutes = [str(item) for item in last.index]
    prices = last.to_numpy(dtype=float)
    returns = []
    for index in range(1, len(minutes)):
        if _minute_ord(minutes[index]) - _minute_ord(minutes[index - 1]) != 1:
            continue
        prev_px = float(prices[index - 1])
        px = float(prices[index])
        if prev_px <= 0 or px <= 0:
            continue
        returns.append(math.log(px / prev_px))
    if not returns:
        return empty
    arr = np.asarray(returns, dtype=float)
    square_sum = float(np.sum(arr * arr))
    if square_sum <= 0:
        return empty
    return {
        "l2_rv": _finite(math.sqrt(square_sum)),
        "l2_rskew": _finite(float(np.sum(arr ** 3) / (square_sum ** 1.5))),
    }


def _official_prices(snapshot: pd.DataFrame) -> dict[str, float]:
    result = {"open": _NAN, "close": _NAN, "prev_close": _NAN}
    if snapshot is None or len(snapshot) == 0:
        return result
    result["open"] = _last_positive(snapshot, "开盘价")
    result["close"] = _last_positive(snapshot, "成交价")
    result["prev_close"] = _last_positive(snapshot, "前收盘")
    return result


def _last_positive(frame: pd.DataFrame, column: str) -> float:
    if column not in frame.columns:
        return _NAN
    values = pd.to_numeric(frame[column], errors="coerce")
    values = values[values > 0]
    if len(values) == 0:
        return _NAN
    return float(values.iloc[-1]) / PRICE_SCALE


def _with_price(trades: pd.DataFrame) -> pd.DataFrame:
    if trades is None or len(trades) == 0 or "成交价格" not in trades.columns:
        return pd.DataFrame(columns=["时间", "price"])
    frame = trades.copy()
    frame["price"] = pd.to_numeric(frame["成交价格"], errors="coerce") / PRICE_SCALE
    return frame


def _first_price(trades: pd.DataFrame, start: str) -> float:
    return _edge_price(trades, start, last=False)


def _last_price(trades: pd.DataFrame, start: str) -> float:
    return _edge_price(trades, start, last=True)


def _last_price_between(trades: pd.DataFrame, start: str, end: str) -> float:
    if len(trades) == 0 or "时间" not in trades.columns:
        return _NAN
    clock = as_time(trades["时间"])
    rows = trades.loc[(clock >= start) & (clock <= end) & (trades["price"] > 0)]
    if len(rows) == 0:
        return _NAN
    return float(rows["price"].iloc[-1])


def _edge_price(trades: pd.DataFrame, start: str, *, last: bool) -> float:
    if len(trades) == 0 or "时间" not in trades.columns:
        return _NAN
    clock = as_time(trades["时间"])
    rows = trades.loc[(clock >= start) & (trades["price"] > 0)]
    if len(rows) == 0:
        return _NAN
    return float(rows["price"].iloc[-1 if last else 0])


def _minute_ord(hhmm: str) -> int:
    text = str(hhmm).zfill(4)
    return int(text[:2]) * 60 + int(text[2:4])


def _ratio(numerator: float, denominator: float) -> float:
    if not math.isfinite(numerator) or not math.isfinite(denominator) or denominator <= 0:
        return _NAN
    return _finite(numerator / denominator - 1.0)


def _finite(value: float) -> float:
    return value if math.isfinite(value) else _NAN
