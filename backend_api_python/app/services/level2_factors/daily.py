"""单日因子行：盘口、成交、竞价和收益拼成 dict。"""
from __future__ import annotations

import math

import pandas as pd

from .flow import cancel_ratio, trade_flow_factors
from .names import BASE_FACTORS
from .session import auction_amount, auction_imbalance, realized_moments, session_returns
from .snapshot import snapshot_factors

_NAN = float("nan")


def empty_factors(code: str, trade_date: str) -> dict[str, object]:
    """缺明细时仍保留全部列，避免某一天的 Parquet 缺字段。"""
    row: dict[str, object] = {"trade_date": trade_date, "symbol": code}
    for name in BASE_FACTORS:
        row[name] = _NAN
    return row


def calc_daily_factors(
    snapshot: pd.DataFrame,
    trades: pd.DataFrame,
    orders: pd.DataFrame,
    code: str,
    trade_date: str,
) -> dict[str, object]:
    """计算一只股票一个交易日的基础因子。金额单位是元，收益是小数。

    ``snapshot`` / ``trades`` / ``orders`` 可以是空表。空表对应因子为 NaN，不抛异常。
    """
    row = empty_factors(code, trade_date)
    snapshot = snapshot if isinstance(snapshot, pd.DataFrame) else pd.DataFrame()
    trades = trades if isinstance(trades, pd.DataFrame) else pd.DataFrame()
    orders = orders if isinstance(orders, pd.DataFrame) else pd.DataFrame()

    row.update(snapshot_factors(snapshot))
    row.update(trade_flow_factors(trades, code))
    row["l2_cancel_ratio"] = cancel_ratio(trades, orders, code)
    row["l2_auction_amount"] = auction_amount(trades)
    row["l2_auction_imbalance"] = auction_imbalance(orders, trades, code)
    row.update(session_returns(snapshot, trades, code))
    row.update(realized_moments(trades, code))
    for name in BASE_FACTORS:
        value = row.get(name, _NAN)
        if value is None or (isinstance(value, float) and not math.isfinite(value)):
            row[name] = _NAN
    return row
