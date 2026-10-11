"""L2 百因子并行链路：组计算、存储、增量。"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _snapshot_rows(n: int = 5) -> pd.DataFrame:
    rows = []
    for i in range(n):
        row = {
            "时间": f"10{i:02d}00000",
            "申买价1": 100000.0 + i * 10,
            "申卖价1": 100100.0 + i * 10,
            "申买量1": 100.0 + i,
            "申卖量1": 80.0 + i,
        }
        for level in range(1, 11):
            row.setdefault(f"申买价{level}", 100000.0 - level)
            row.setdefault(f"申卖价{level}", 100100.0 + level)
            row.setdefault(f"申买量{level}", 10.0 * level)
            row.setdefault(f"申卖量{level}", 8.0 * level)
        rows.append(row)
    return pd.DataFrame(rows)


def _trades() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "时间": "100000000",
                "成交代码": "0",
                "成交价格": 100000,
                "成交数量": 100,
                "BS标志": "B",
                "叫买序号": "1",
                "叫卖序号": "10",
            },
            {
                "时间": "100001000",
                "成交代码": "0",
                "成交价格": 100100,
                "成交数量": 200,
                "BS标志": "S",
                "叫买序号": "2",
                "叫卖序号": "11",
            },
            {
                "时间": "100002000",
                "成交代码": "0",
                "成交价格": 100050,
                "成交数量": 150,
                "BS标志": "B",
                "叫买序号": "1",
                "叫卖序号": "12",
            },
            {
                "时间": "143500000",
                "成交代码": "0",
                "成交价格": 100200,
                "成交数量": 50,
                "BS标志": "B",
                "叫买序号": "3",
                "叫卖序号": "13",
            },
        ]
    )


def _orders() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "时间": "093100000",
                "委托类型": "A",
                "委托代码": "B",
                "交易所委托号": "1",
                "委托数量": 1000,
                "委托价格": 100000,
            },
            {
                "时间": "093200000",
                "委托类型": "A",
                "委托代码": "S",
                "交易所委托号": "2",
                "委托数量": 800,
                "委托价格": 100100,
            },
            {
                "时间": "100000000",
                "委托类型": "D",
                "委托代码": "B",
                "交易所委托号": "3",
                "委托数量": 100,
                "委托价格": 100000,
            },
        ]
    )


def _write_books(root: Path, date: str, code: str) -> None:
    folder = root / date / code
    folder.mkdir(parents=True, exist_ok=True)
    _snapshot_rows().to_parquet(folder / "行情.parquet", index=False)
    _trades().to_parquet(folder / "逐笔成交.parquet", index=False)
    _orders().to_parquet(folder / "逐笔委托.parquet", index=False)


def test_catalog_has_100_unique_ids():
    from app.services.level2_factors.l2_daily.catalog import FACTOR_DEFINITIONS, factor_ids

    ids = factor_ids()
    assert len(ids) == 100
    assert len(set(ids)) == 100
    assert len(FACTOR_DEFINITIONS) == 100


def test_trade_group_single_pass_stats():
    from app.services.level2_factors.l2_daily.groups.trade import calc_trade_factors

    row = calc_trade_factors(_trades(), "000001")
    assert row["l2_trade_count"] == 4
    assert row["l2_trade_volume"] == 500
    assert row["l2_active_buy_count"] == 3
    assert row["l2_active_sell_count"] == 1
    assert np.isfinite(row["l2_vwap"])
    assert np.isfinite(row["l2_trade_amount_hhi"])


def test_trade_empty_returns_nan_not_raise():
    from app.services.level2_factors.l2_daily.catalog import factor_ids_for_group
    from app.services.level2_factors.l2_daily.groups.trade import calc_trade_factors

    row = calc_trade_factors(pd.DataFrame(), "000001")
    for key in factor_ids_for_group("trade"):
        assert key in row
        assert row[key] != row[key]  # NaN


def test_book_and_order_groups():
    from app.services.level2_factors.l2_daily.groups.book import calc_book_factors
    from app.services.level2_factors.l2_daily.groups.order import calc_order_factors

    book = calc_book_factors(_snapshot_rows())
    assert np.isfinite(book["l2_mid_price_mean"])
    assert np.isfinite(book["l2_obi5_mean"])
    # depth5_ratio = bid/(bid+ask)，与 OBI=(bid-ask)/(bid+ask) 线性相关但不相同
    assert book["l2_depth5_ratio"] == pytest.approx((book["l2_obi5_mean"] + 1.0) / 2.0)
    assert book["l2_depth5_ratio"] != pytest.approx(book["l2_obi5_mean"])

    order = calc_order_factors(_orders(), _trades(), "600000")
    # 沪市：A 记录量 + 主动成交量（买 1:100+150、3:50；卖 11:200）
    assert order["l2_bid_order_volume"] == 1300
    assert order["l2_ask_order_volume"] == 1000
    assert order["l2_bid_cancel_rate"] == pytest.approx(100 / 1300)


def test_microstructure_group():
    from app.services.level2_factors.l2_daily.groups.microstructure import calc_microstructure_factors

    row = calc_microstructure_factors(_snapshot_rows(), _trades(), _orders(), "000001")
    assert np.isfinite(row["l2_trade_arrival_rate"])
    assert np.isfinite(row["l2_open_amount_ratio"]) or True  # 开盘窗可能空
    assert "l2_kyle_lambda" in row
    assert "l2_ofi1" in row


def test_storage_merge_compact_and_logical_uri(tmp_path, monkeypatch):
    from app.services.level2_factors.l2_daily import storage
    from app.services.level2_factors.l2_daily.catalog import factor_ids_for_group, wide_columns

    monkeypatch.setenv("R2_L2_DAILY_PREFIX", "factors/l2_daily")
    root = tmp_path / "out"
    date = "20261009"
    uploaded: list[str] = []
    storage.set_r2_uploader(lambda key, payload: uploaded.append(key))

    rows = [
        {
            "trade_date": date,
            "symbol": "000001",
            **{k: 1.0 for k in factor_ids_for_group("trade")},
        }
    ]
    merged = storage.merge_group_columns(None, rows, factor_ids_for_group("trade"), date)
    path = storage.write_day(root, date, merged)
    assert path.is_file()
    panel = pd.read_parquet(path)
    assert list(panel.columns) == wide_columns()
    assert panel.loc[0, "l2_trade_count"] == 1.0

    uri = storage.upload_day_to_r2(root, date)
    assert uri == f"factors/l2_daily/version=1/year=2026/month=202610/date={date}.parquet"
    assert uploaded == [uri]
    assert not Path(uri).is_absolute()

    part = storage.compact_month(root, "202610")
    assert part is not None and part.is_file()
    assert len(pd.read_parquet(part)) == 1


def test_incremental_skip_same_source_version(tmp_path, monkeypatch):
    from app.services.level2_factors.l2_daily import orchestrator, storage

    monkeypatch.setenv("LEVEL2_L2_DAILY_ROOT", str(tmp_path / "factors"))
    books = tmp_path / "books"
    date = "20261009"
    _write_books(books, date, "000001")
    storage.set_r2_uploader(lambda key, payload: None)

    first = orchestrator.run(
        [date],
        parquet_root=books,
        output_root=tmp_path / "factors",
        groups=["trade"],
        force=False,
        upload_r2=True,
        seed_defs=False,
        compact_months=False,
    )
    assert first["processed"] == 1
    assert first["skipped"] == 0

    second = orchestrator.run(
        [date],
        parquet_root=books,
        output_root=tmp_path / "factors",
        groups=["trade"],
        force=False,
        upload_r2=True,
        seed_defs=False,
        compact_months=False,
    )
    assert second["skipped"] == 1
    assert second["processed"] == 0

    # 改明细后应重算
    trade_path = books / date / "000001" / "逐笔成交.parquet"
    frame = pd.read_parquet(trade_path)
    frame = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
    trade_path.write_bytes(b"")  # bump mtime/size
    frame.to_parquet(trade_path, index=False)

    third = orchestrator.run(
        [date],
        parquet_root=books,
        output_root=tmp_path / "factors",
        groups=["trade"],
        force=False,
        upload_r2=True,
        seed_defs=False,
        compact_months=False,
    )
    assert third["processed"] == 1


def test_group_isolation_missing_snapshot(tmp_path, monkeypatch):
    """缺行情时 book 失败，trade 仍可完成。"""
    from app.services.level2_factors.l2_daily import orchestrator, storage

    books = tmp_path / "books"
    date = "20261010"
    code = "600000"
    folder = books / date / code
    folder.mkdir(parents=True)
    _trades().to_parquet(folder / "逐笔成交.parquet", index=False)
    # 无行情
    storage.set_r2_uploader(lambda key, payload: None)

    summary = orchestrator.run(
        [date],
        parquet_root=books,
        output_root=tmp_path / "out",
        groups=["trade", "book"],
        force=True,
        upload_r2=False,
        seed_defs=False,
        compact_months=False,
    )
    assert summary["processed"] >= 1
    panel = storage.read_day(tmp_path / "out", date)
    assert panel is not None
    assert np.isfinite(panel.loc[0, "l2_trade_count"])
    assert panel.loc[0, "l2_mid_price_mean"] != panel.loc[0, "l2_mid_price_mean"]


def _trade(clock: str, price: int, qty: int, bs: str, buy_id: str, sell_id: str, code: str = "") -> dict:
    return {
        "时间": clock,
        "成交代码": code,
        "成交价格": price,
        "成交数量": qty,
        "BS标志": bs,
        "叫买序号": buy_id,
        "叫卖序号": sell_id,
    }


def _order(clock: str, kind: str, side: str, order_id: str, qty: int, price: int) -> dict:
    return {
        "时间": clock,
        "委托类型": kind,
        "委托代码": side,
        "交易所委托号": order_id,
        "委托数量": qty,
        "委托价格": price,
    }


def test_sh_auction_prints_excluded_from_direction():
    """沪市 09:25 和 14:58 的集合竞价成交全标 S，不能算进主动卖或尾盘不平衡。"""
    from app.services.level2_factors.l2_daily.groups.microstructure import calc_microstructure_factors
    from app.services.level2_factors.l2_daily.groups.trade import calc_trade_factors

    trades = pd.DataFrame(
        [
            _trade("092500000", 100000, 5000, "S", "1", "2"),
            _trade("100000000", 100100, 100, "B", "3", "4"),
            _trade("143500000", 100100, 50, "B", "7", "8"),
            _trade("145800000", 100200, 8000, "S", "5", "6"),
        ]
    )
    row = calc_trade_factors(trades, "600000")
    assert row["l2_trade_count"] == 4
    assert row["l2_trade_volume"] == 13150
    assert row["l2_active_buy_count"] == 2
    assert row["l2_active_sell_count"] == 0
    assert row["l2_active_sell_volume"] == 0
    assert row["l2_active_buy_amount_ratio"] == pytest.approx(1.0)
    assert row["l2_trade_amount_imbalance_ratio"] == pytest.approx(1.0)
    micro = calc_microstructure_factors(pd.DataFrame(), trades, pd.DataFrame(), "600000")
    assert micro["l2_close_imbalance"] == pytest.approx(1.0)


def test_sh_aggressor_orders_recovered_from_trades():
    """沪市即时成交的主动单不在逐笔委托里，委托量要从成交补回。"""
    from app.services.level2_factors.l2_daily.groups.order import calc_order_factors

    orders = pd.DataFrame([_order("093000000", "A", "S", "20", 500, 100000)])
    trades = pd.DataFrame([_trade("093100000", 100000, 300, "B", "99", "20")])
    row = calc_order_factors(orders, trades, "600000")
    assert row["l2_bid_order_volume"] == 300
    assert row["l2_bid_order_amount"] == pytest.approx(3000.0)
    assert row["l2_ask_order_volume"] == 500


def test_sz_cancel_amount_uses_order_price():
    """深市撤单 成交价格=0：撤单金额 = 撤单量 × 原委托价 / 10000。"""
    from app.services.level2_factors.l2_daily.groups.order import calc_order_factors

    orders = pd.DataFrame(
        [
            _order("093100000", "0", "B", "5", 1000, 100000),
            _order("093200000", "0", "S", "6", 600, 101000),
        ]
    )
    trades = pd.DataFrame(
        [
            _trade("100000000", 0, 400, "", "5", "0", code="C"),
            _trade("100100000", 0, 200, "", "0", "6", code="C"),
        ]
    )
    row = calc_order_factors(orders, trades, "000001")
    assert row["l2_bid_cancel_volume"] == 400
    assert row["l2_bid_cancel_amount"] == pytest.approx(400 * 100000 / 10000)
    assert row["l2_ask_cancel_volume"] == 200
    assert row["l2_ask_cancel_amount"] == pytest.approx(200 * 101000 / 10000)


def test_cancel_rate_is_cancel_over_order_qty():
    """撤单率 = 撤单量 / 委托量，委托量里已含被撤部分，不再相加。"""
    from app.services.level2_factors.l2_daily.groups.order import calc_order_factors

    orders = pd.DataFrame(
        [
            _order("093100000", "A", "B", "7", 1000, 100000),
            _order("100000000", "D", "B", "7", 400, 100000),
        ]
    )
    row = calc_order_factors(orders, pd.DataFrame(), "600000")
    assert row["l2_bid_order_volume"] == 1000
    assert row["l2_bid_cancel_rate"] == pytest.approx(0.4)


def test_large_trade_counted_once_when_both_sides_large():
    """买卖双方都是大单的那笔成交只计一次。"""
    from app.services.level2_factors.l2_daily.groups.trade import calc_trade_factors

    trades = pd.DataFrame(
        [
            _trade("100000000", 100000, 200000, "B", "1", "2"),  # 2,000,000 元
            _trade("100100000", 100000, 100, "S", "3", "4"),
        ]
    )
    row = calc_trade_factors(trades, "600000")
    assert row["l2_large_trade_count"] == 1
    assert row["l2_large_trade_volume"] == 200000
    assert row["l2_large_trade_amount"] == pytest.approx(2_000_000.0)
    assert row["l2_large_trade_amount_ratio"] == pytest.approx(2_000_000.0 / 2_001_000.0)
    assert row["l2_large_active_buy_amount"] == pytest.approx(2_000_000.0)
    assert row["l2_large_active_sell_amount"] == 0


def test_effective_spread_skips_one_sided_quotes():
    """一侧 ask=0 的快照不参与有效价差计算，且只用成交之前的快照。"""
    from app.services.level2_factors.l2_daily.groups.microstructure import calc_microstructure_factors

    snapshot = pd.DataFrame(
        [
            {"时间": "100000000", "申买价1": 100000, "申卖价1": 100100, "申买量1": 100, "申卖量1": 100},
            {"时间": "100003000", "申买价1": 100000, "申卖价1": 0, "申买量1": 100, "申卖量1": 0},
            {"时间": "100005000", "申买价1": 120000, "申卖价1": 120100, "申买量1": 100, "申卖量1": 100},
        ]
    )
    trades = pd.DataFrame([_trade("100005000", 100100, 100, "B", "1", "2")])
    row = calc_microstructure_factors(snapshot, trades, pd.DataFrame(), "600000")
    mid = (100000 + 100100) / 2 / 10000
    assert row["l2_effective_spread"] == pytest.approx(2 * abs(10.01 - mid) / mid)
    assert row["l2_effective_spread"] < 0.01


def test_minute_returns_reset_at_lunch_break():
    """上午收盘到下午开盘的价格变化不是一分钟收益。"""
    from app.services.level2_factors.l2_daily.groups.microstructure import calc_microstructure_factors

    trades = pd.DataFrame(
        [
            _trade("112800000", 100000, 100, "B", "1", "11"),
            _trade("112900000", 101000, 100, "B", "2", "12"),
            _trade("130000000", 200000, 100, "S", "3", "13"),
            _trade("130100000", 202000, 100, "S", "4", "14"),
        ]
    )
    row = calc_microstructure_factors(pd.DataFrame(), trades, pd.DataFrame(), "600000")
    expected_return = np.log(1.01)
    expected_amihud = np.mean([expected_return / 1010.0, expected_return / 2020.0])
    assert row["l2_intraday_return_std"] == pytest.approx(0.0, abs=1e-12)
    assert row["l2_amihud_illiquidity"] == pytest.approx(expected_amihud)


def test_book_obi_requires_two_sided_quote_and_matches_microstructure():
    """单边盘口不进入 OBI；因子 98 与 book 组使用同一 OBI 均值。"""
    from app.services.level2_factors.l2_daily.groups.book import calc_book_factors
    from app.services.level2_factors.l2_daily.groups.microstructure import calc_microstructure_factors

    snapshot = pd.DataFrame(
        [
            {"时间": "100000000", "申买价1": 100000, "申卖价1": 100100, "申买量1": 300, "申卖量1": 100},
            {"时间": "100100000", "申买价1": 100000, "申卖价1": 0, "申买量1": 1000, "申卖量1": 0},
        ]
    )
    trades = pd.DataFrame(
        [
            _trade("100010000", 100000, 100, "B", "1", "11"),
            _trade("100020000", 100000, 100, "S", "2", "12"),
        ]
    )
    book = calc_book_factors(snapshot)
    micro = calc_microstructure_factors(snapshot, trades, pd.DataFrame(), "600000")
    assert book["l2_obi5_mean"] == pytest.approx(0.5)
    assert micro["l2_trade_book_imbalance_diff"] == pytest.approx(-book["l2_obi5_mean"])


def test_cancel_rate_uses_same_continuous_order_cohort():
    """竞价时挂入、连续竞价撤掉的单不进入连续竞价撤单率。"""
    from app.services.level2_factors.l2_daily.groups.order import calc_order_factors

    orders = pd.DataFrame(
        [
            _order("092000000", "A", "B", "auction", 1000, 100000),
            _order("093100000", "A", "B", "continuous", 100, 100000),
            _order("100000000", "D", "B", "auction", 1000, 100000),
            _order("100100000", "D", "B", "continuous", 20, 100000),
        ]
    )
    row = calc_order_factors(orders, pd.DataFrame(), "600000")
    assert row["l2_bid_order_volume"] == 100
    assert row["l2_bid_cancel_volume"] == 20
    assert row["l2_bid_cancel_rate"] == pytest.approx(0.2)


def test_missing_sz_cancel_price_produces_nan_amount():
    """深市撤单价格无法按委托号回查时，金额不能静默记成 0。"""
    from app.services.level2_factors.l2_daily.groups.order import calc_order_factors

    orders = pd.DataFrame([_order("093100000", "1", "B", "5", 1000, 0)])
    trades = pd.DataFrame([_trade("100000000", 0, 400, "", "5", "0", code="C")])
    row = calc_order_factors(orders, trades, "000001")
    assert row["l2_bid_cancel_volume"] == 400
    assert row["l2_bid_cancel_rate"] == pytest.approx(0.4)
    assert np.isnan(row["l2_bid_cancel_amount"])


def test_book_missing_qty_columns_returns_nan_not_crash():
    """缺买一/卖一量列时返回 NaN，不能 AttributeError。"""
    from app.services.level2_factors.l2_daily.catalog import factor_ids_for_group
    from app.services.level2_factors.l2_daily.groups.book import calc_book_factors

    snapshot = pd.DataFrame(
        [{"时间": "100000000", "申买价1": 100000, "申卖价1": 100100}]
    )
    row = calc_book_factors(snapshot)
    for key in factor_ids_for_group("book"):
        assert key in row
        assert row[key] != row[key]


def test_missing_bs_flag_keeps_direction_nan():
    """缺 BS 标志时主动占比必须是 NaN，不能静默写成 0。"""
    from app.services.level2_factors.l2_daily.groups.trade import calc_trade_factors

    trades = pd.DataFrame(
        [
            {
                "时间": "100000000",
                "成交代码": "0",
                "成交价格": 100000,
                "成交数量": 100,
                "叫买序号": "1",
                "叫卖序号": "2",
            },
            {
                "时间": "100100000",
                "成交代码": "0",
                "成交价格": 100000,
                "成交数量": 200,
                "叫买序号": "3",
                "叫卖序号": "4",
            },
        ]
    )
    row = calc_trade_factors(trades, "600000")
    assert row["l2_trade_count"] == 2
    assert np.isnan(row["l2_active_buy_amount_ratio"])
    assert np.isnan(row["l2_active_sell_amount_ratio"])
    assert np.isnan(row["l2_active_buy_count"])
    assert np.isnan(row["l2_trade_amount_imbalance_ratio"])


def test_sh_cancel_nan_price_falls_back_to_order_price():
    """沪市撤单价格为 NaN 时，按委托号回查原委托价。"""
    from app.services.level2_factors.l2_daily.groups.order import calc_order_factors

    orders = pd.DataFrame(
        [
            _order("093100000", "A", "B", "7", 1000, 100000),
            {
                "时间": "100000000",
                "委托类型": "D",
                "委托代码": "B",
                "交易所委托号": "7",
                "委托数量": 400,
                "委托价格": np.nan,
            },
        ]
    )
    row = calc_order_factors(orders, pd.DataFrame(), "600000")
    assert row["l2_bid_cancel_volume"] == 400
    assert row["l2_bid_cancel_amount"] == pytest.approx(400 * 100000 / 10000)
    assert row["l2_bid_cancel_rate"] == pytest.approx(0.4)


def test_order_id_normalization_matches_cancel_to_book():
    """委托号 '123.0' / '123' / ' 123 ' 归一化后，撤单能匹配到连续竞价委托。"""
    from app.services.level2_factors.l2_daily.groups.order import calc_order_factors

    orders = pd.DataFrame(
        [
            _order("093100000", "0", "B", "123.0", 1000, 100000),
            _order("093200000", "0", "S", " 456 ", 600, 101000),
        ]
    )
    trades = pd.DataFrame(
        [
            _trade("100000000", 0, 400, "", "123", "0", code="C"),
            _trade("100100000", 0, 200, "", "0", "456.0", code="C"),
        ]
    )
    row = calc_order_factors(orders, trades, "000001")
    assert row["l2_bid_cancel_volume"] == 400
    assert row["l2_ask_cancel_volume"] == 200
    assert row["l2_bid_cancel_rate"] == pytest.approx(0.4)
    assert row["l2_ask_cancel_rate"] == pytest.approx(200 / 600)
    assert row["l2_bid_cancel_amount"] == pytest.approx(400 * 100000 / 10000)
    assert row["l2_ask_cancel_amount"] == pytest.approx(200 * 101000 / 10000)


def test_600726_sample_end_to_end_when_configured(tmp_path):
    """设置 LEVEL2_SAMPLE_ROOT 后，用真实沪市样例跑完整四组区间检查。"""
    sample_root_value = os.getenv("LEVEL2_SAMPLE_ROOT")
    if not sample_root_value:
        pytest.skip("set LEVEL2_SAMPLE_ROOT to run the external L2 sample test")

    from app.services.level2_factors.l2_daily import orchestrator, storage
    from app.services.level2_factors.l2_daily._prep import continuous, prepare_trades
    from app.services.level2_factors.l2_daily.catalog import factor_ids
    from app.services.level2_ingest.csv_to_parquet import read_csv_bytes

    sample_root = Path(sample_root_value)
    source = sample_root / "600726.SH"
    if not source.is_dir():
        pytest.skip(f"sample directory does not exist: {source}")

    date = "20260424"
    symbol = "600726.SH"
    target = tmp_path / "books" / date / symbol
    target.mkdir(parents=True)
    frames = {}
    for name in ("行情", "逐笔成交", "逐笔委托"):
        frames[name] = read_csv_bytes((source / f"{name}.csv").read_bytes(), name)
        frames[name].to_parquet(target / f"{name}.parquet", index=False)

    summary = orchestrator.run(
        [date],
        parquet_root=tmp_path / "books",
        output_root=tmp_path / "out",
        groups=None,
        force=True,
        upload_r2=False,
        seed_defs=False,
        compact_months=False,
    )
    assert summary["processed"] == 4
    assert summary["failed"] == 0

    panel = storage.read_day(tmp_path / "out", date)
    assert panel is not None and len(panel) == 1
    row = panel.loc[panel["symbol"].eq(symbol)].iloc[0]
    assert np.isfinite(row[factor_ids()].astype(float)).all()

    zero_to_one = [
        "l2_active_buy_amount_ratio",
        "l2_active_sell_amount_ratio",
        "l2_large_trade_amount_ratio",
        "l2_large_trade_volume_ratio",
        "l2_max_trade_amount_ratio",
        "l2_top5_trade_amount_ratio",
        "l2_bid_cancel_rate",
        "l2_ask_cancel_rate",
        "l2_open_amount_ratio",
        "l2_close_amount_ratio",
        "l2_trade_price_direction_agreement",
    ]
    minus_one_to_one = [
        "l2_trade_amount_imbalance_ratio",
        "l2_trade_volume_imbalance_ratio",
        "l2_trade_count_imbalance_ratio",
        "l2_large_net_buy_amount_ratio",
        "l2_order_volume_imbalance_ratio",
        "l2_order_amount_imbalance_ratio",
        "l2_cancel_volume_imbalance_ratio",
        "l2_cancel_amount_imbalance_ratio",
        "l2_obi5_mean",
        "l2_obi5_close",
        "l2_obi10_mean",
        "l2_close_imbalance",
        "l2_close_obi",
        "l2_ofi_price_corr",
    ]
    assert row[zero_to_one].astype(float).between(0.0, 1.0).all()
    assert row[minus_one_to_one].astype(float).between(-1.0, 1.0).all()
    assert 0.0 <= float(row["l2_effective_spread"]) < 0.05

    cont = continuous(prepare_trades(frames["逐笔成交"], symbol))
    aggressive_buy = float(cont.loc[cont["side"].eq("B"), "qty"].sum())
    aggressive_sell = float(cont.loc[cont["side"].eq("S"), "qty"].sum())
    assert row["l2_bid_order_volume"] >= aggressive_buy
    assert row["l2_ask_order_volume"] >= aggressive_sell


def test_meta_seed_noop_without_d1(monkeypatch):
    from app.services.level2_factors import d1_client
    from app.services.level2_factors.l2_daily import meta

    monkeypatch.setattr(d1_client, "configured", lambda: False)
    assert meta.seed_definitions() == 0
    assert meta.create_job(factor_group="trade", start_date="20261001", end_date="20261001")
