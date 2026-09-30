"""大单委托聚合：按叫买/叫卖序号汇总成交，对齐 l2_read.wt_cj 口径。

官方 l2_read 以「委托号聚合后的成交金额」判断大单，而非单笔成交金额。
"""
from __future__ import annotations

import pandas as pd


def _valid_order_id(series: pd.Series) -> pd.Series:
    """过滤无效委托序号（0/nan/空）。"""
    s = series.astype(str).str.strip()
    return s.ne("") & ~s.isin(["0", "nan", "None", "NaN"])


def aggregate_trades_by_order(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """将连续竞价成交按叫买/叫卖序号聚合为委托级买卖两表。

    返回 (buy_orders, sell_orders)，列含 order_id, amount, volume, bs_flag。
    """
    buy = trades.loc[_valid_order_id(trades["叫买序号"])].copy()
    sell = trades.loc[_valid_order_id(trades["叫卖序号"])].copy()

    buy_agg = (
        buy.groupby("叫买序号", as_index=False)
        .agg(amount=("amount", "sum"), volume=("成交数量", "sum"))
        .rename(columns={"叫买序号": "order_id"})
    )
    buy_agg["bs_flag"] = "B"

    sell_agg = (
        sell.groupby("叫卖序号", as_index=False)
        .agg(amount=("amount", "sum"), volume=("成交数量", "sum"))
        .rename(columns={"叫卖序号": "order_id"})
    )
    sell_agg["bs_flag"] = "S"

    return buy_agg, sell_agg


def big_order_flow(trades: pd.DataFrame, threshold: float) -> dict[str, float]:
    """按委托聚合后计算大单买卖金额与量（元/股）。"""
    buy_agg, sell_agg = aggregate_trades_by_order(trades)
    big_buy = buy_agg[buy_agg["amount"] >= threshold]
    big_sell = sell_agg[sell_agg["amount"] >= threshold]

    big_buy_amount = float(big_buy["amount"].sum())
    big_sell_amount = float(big_sell["amount"].sum())

    return {
        "big_buy_amount": big_buy_amount,
        "big_sell_amount": big_sell_amount,
        "big_net_inflow": big_buy_amount - big_sell_amount,
        "big_buy_volume": float(big_buy["volume"].sum()),
        "big_sell_volume": float(big_sell["volume"].sum()),
    }


def merge_orders_with_trades_sz(
    orders: pd.DataFrame, trades: pd.DataFrame
) -> pd.DataFrame:
    """深市委托与成交关联（对齐 l2_read.wt_cj）：剔除 D 类撤单后 merge。"""
    buy_g = trades.groupby("叫买序号").agg({"成交数量": "sum", "amount": "sum"})
    sell_g = trades.groupby("叫卖序号").agg({"成交数量": "sum", "amount": "sum"})
    cj = pd.concat([sell_g, buy_g])
    cj = cj.reset_index().rename(columns={"index": "交易所委托号"})
    cj["交易所委托号"] = cj["交易所委托号"].astype(str)

    wt = orders[orders["委托类型"].astype(str).ne("D")].copy()
    wt["交易所委托号"] = wt["交易所委托号"].astype(str)
    merged = pd.merge(wt, cj, on="交易所委托号", how="inner")
    merged["委托金额"] = merged["委托价格"] * merged["委托数量"] / 10000.0
    merged = merged.rename(columns={"amount": "成交金额"})
    return merged


def estimate_threshold_from_orders(trades: pd.DataFrame, quantile: float,
                                   min_amt: float, max_amt: float) -> float:
    """基于委托聚合金额的 quantile 估计大单阈值。"""
    buy_agg, sell_agg = aggregate_trades_by_order(trades)
    amounts = pd.concat([buy_agg["amount"], sell_agg["amount"]], ignore_index=True)
    if len(amounts) == 0:
        return min_amt
    q = float(amounts.quantile(quantile))
    return float(min(max(q, min_amt), max_amt))
