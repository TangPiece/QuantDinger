"""日频因子口径：竞价窗口收到 09:25，部分撤单按量扣，未补零时间不进连续竞价。"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from app.services.factors.level2_catalog import base_factor_ids
from app.services.level2_factors.daily import calc_daily_factors
from app.services.level2_factors.names import BASE_FACTORS
from app.services.level2_factors.snapshot import snapshot_factors


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


def _book(clock: str, *, bid_size: float = 10.0, ask_size: float = 20.0, bid_price: float = 100.0, ask_price: float = 101.0) -> dict:
    """十档同价同量的一帧行情。价格用元，和真实盘口的万分之一价格只差一个常数。"""
    row = {"时间": clock}
    for level in range(1, 11):
        row[f"申买价{level}"] = bid_price
        row[f"申卖价{level}"] = ask_price
        row[f"申买量{level}"] = bid_size
        row[f"申卖量{level}"] = ask_size
    return row


def test_ofi_same_price_bid_increase_is_depth_normalized():
    """价不变时 OFI 等于数量差。十档权重合计为 1，再除以后一帧的十档总深度。"""
    frame = pd.DataFrame([
        _book("100000000", bid_size=10.0, ask_size=20.0),
        _book("100003000", bid_size=20.0, ask_size=20.0),
    ])
    # 每档买量 +10，加权后仍是 10。后一帧深度 = 20*10 + 20*10。
    assert snapshot_factors(frame)["l2_ofi"] == pytest.approx(10.0 / 400.0)


def test_ofi_bid_price_up_counts_only_new_size_and_inside_weight():
    """买一价上移只记新挂量，且第 1 档权重是 10/55。其余档价量不变，贡献 0。"""
    first = _book("100000000")
    second = _book("100003000")
    second["申买价1"] = 102.0
    value = snapshot_factors(pd.DataFrame([first, second]))["l2_ofi"]
    # 第 1 档贡献 +10，权重 10/55。后一帧深度仍是 10*10 + 20*10。
    assert value == pytest.approx((10.0 * 10.0 / 55.0) / 300.0)


def test_ofi_ask_price_down_is_selling_pressure():
    """卖一价下移只记新卖量，符号为负。其余档价量不变。"""
    first = _book("100000000")
    second = _book("100003000")
    second["申卖价1"] = 100.0
    second["申卖量1"] = 30.0
    value = snapshot_factors(pd.DataFrame([first, second]))["l2_ofi"]
    later_depth = 10.0 * 10 + (30.0 + 20.0 * 9)
    assert value == pytest.approx((-30.0 * 10.0 / 55.0) / later_depth)


def test_ofi_skips_lunch_gap_and_single_snapshot():
    """午休两边不连；只有一帧时没有差分，结果为空。"""
    lunch = pd.DataFrame([
        _book("113000000", bid_size=10.0),
        _book("130000000", bid_size=80.0),
    ])
    assert math.isnan(snapshot_factors(lunch)["l2_ofi"])
    assert math.isnan(snapshot_factors(pd.DataFrame([_book("100000000")]))["l2_ofi"])

    mixed = pd.DataFrame([
        _book("100000000", bid_size=10.0, ask_size=20.0),
        _book("100003000", bid_size=20.0, ask_size=20.0),
        _book("113000000", bid_size=20.0, ask_size=20.0),
        _book("130000000", bid_size=100.0, ask_size=20.0),
        _book("130003000", bid_size=100.0, ask_size=20.0),
    ])
    # 只有 10:00 那一跳贡献 10；13:00 价平量平贡献 0。深度分别是 400 和 1200。
    assert snapshot_factors(mixed)["l2_ofi"] == pytest.approx(10.0 / ((400.0 + 1200.0) / 2.0))


def test_ofi_column_is_registered_with_catalog():
    """落盘列和因子库目录必须同名，否则日表写得进、界面选不中。"""
    assert "l2_ofi" in BASE_FACTORS
    assert base_factor_ids() == BASE_FACTORS
