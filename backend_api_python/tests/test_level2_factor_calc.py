"""日频因子口径：竞价窗口收到 09:25，部分撤单按量扣，未补零时间不进连续竞价。"""
from __future__ import annotations

import pandas as pd
import pytest

from app.services.level2_factors.daily import calc_daily_factors


def _snapshot_row() -> dict:
    row = {
        "时间": "100000000",
        "开盘价": 100000.0,
        "成交价": 101000.0,
        "前收盘": 99000.0,
        "申买价1": 100000.0,
        "申卖价1": 101000.0,
        "叫买总量": 300.0,
        "叫卖总量": 100.0,
    }
    for level in range(1, 11):
        row[f"申买量{level}"] = 10.0
        row[f"申卖量{level}"] = 20.0
    return row


def test_auction_imbalance_keeps_partial_remainder_and_stops_at_0925():
    """只撤一部分时剩余量仍计入；09:25 之后的预挂单不进竞价不平衡。"""
    orders = pd.DataFrame([
        {"时间": "091600000", "委托类型": "A", "委托代码": "B", "交易所委托号": "11", "委托数量": 1000},
        {"时间": "091800000", "委托类型": "D", "委托代码": "B", "交易所委托号": "11", "委托数量": 400},
        {"时间": "091900000", "委托类型": "A", "委托代码": "S", "交易所委托号": "12", "委托数量": 400},
        {"时间": "092600000", "委托类型": "A", "委托代码": "S", "交易所委托号": "13", "委托数量": 5000},
    ])
    trades = pd.DataFrame(columns=["时间", "成交价格", "成交数量", "BS标志", "叫买序号", "叫卖序号"])
    row = calc_daily_factors(pd.DataFrame([_snapshot_row()]), trades, orders, "600000.SH", "20251103")
    assert row["l2_auction_imbalance"] == pytest.approx((600 - 400) / (600 + 400))


def test_unpadded_auction_print_is_not_continuous_volume():
    """未补零的 9:15 成交不能因为字符串比较进主动净买入。空字符的深市成交代码仍算成交。"""
    trades = pd.DataFrame([
        {"时间": "91500000", "成交代码": "0\x00", "成交价格": 100000, "成交数量": 500000, "BS标志": "B", "叫买序号": "1", "叫卖序号": "2"},
        {"时间": "100000000", "成交代码": "0", "成交价格": 100000, "成交数量": 100, "BS标志": "S", "叫买序号": "3", "叫卖序号": "4"},
    ])
    orders = pd.DataFrame(columns=["时间", "委托类型", "委托代码", "交易所委托号", "委托数量"])
    row = calc_daily_factors(pd.DataFrame([_snapshot_row()]), trades, orders, "000001.SZ", "20251103")
    assert row["l2_active_net_buy"] == pytest.approx(-1.0)
