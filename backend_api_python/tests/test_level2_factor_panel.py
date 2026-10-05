"""把离线 Level2 日频面板并进日线，并让 factor()/因子研究能读到这些列。"""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from app.services.factors import compute_factor, list_factors
from app.services.level2_factor_panel import (
    canonical_symbol,
    clear_panel_cache,
    enrich_panel,
    session_dates,
)
from app.services.strategy_v2 import StrategyV2BacktestRunner
from app.services.strategy_v2.service import StrategyV2BacktestService


class _Repository:
    def persist_run(self, **kwargs):
        self.persisted = kwargs
        return 1


def _daily_frame(periods=8, start="2025-11-03"):
    index = pd.date_range(start, periods=periods, freq="D")
    close = np.linspace(10, 12, periods)
    return pd.DataFrame({
        "open": close,
        "high": close + 0.2,
        "low": close - 0.2,
        "close": close,
        "volume": np.full(periods, 1000.0),
    }, index=index)


def test_session_dates_follow_shanghai_trading_day():
    # 上海 2025-11-03 00:00 是 UTC 前一晚 16:00。按 UTC 日历会落到 11-02。
    stamps = pd.to_datetime(["2025-11-02 16:00:00", "2025-11-03 00:00:00"])
    dates = session_dates(stamps)
    assert list(dates.strftime("%Y%m%d")) == ["20251103", "20251103"]


def test_canonical_symbol_adds_exchange_suffix():
    assert canonical_symbol("CNStock:600519") == "600519.SH"
    assert canonical_symbol("000001.XSHE") == "000001.SZ"
    assert canonical_symbol("CNStock:300750.SZ") == "300750.SZ"
    # 腾讯代码带交易所前缀，面板键带后缀。
    assert canonical_symbol("SH600519") == "600519.SH"
    assert canonical_symbol("sz000001") == "000001.SZ"
    assert canonical_symbol("BJ430047") == "430047.BJ"


def test_panel_joins_the_same_session_and_does_not_fill_forward(tmp_path, monkeypatch):
    clear_panel_cache()
    monkeypatch.delenv("LEVEL2_FACTOR_PANEL_DIR", raising=False)
    day = pd.DataFrame({
        "trade_date": ["20251103", "20251105"],
        "symbol": ["600519.SH", "600519.SH"],
        "l2_obi": [0.2, 0.8],
        "l2_active_net_buy": [0.1, -0.3],
    })
    # 日 K 索引按本地午夜写成 unix 再变回 UTC 之前，测试直接用交易日零点。
    index = pd.to_datetime(["2025-11-03", "2025-11-04", "2025-11-05"])
    frame = _daily_frame(3, "2025-11-03")
    frame.index = index
    # 11-03 和 11-05 各写一份，中间一天没有文件，不能用 0.2 填充。
    day.loc[day["trade_date"] == "20251103"].to_parquet(tmp_path / "20251103.parquet", index=False)
    day.loc[day["trade_date"] == "20251105"].to_parquet(tmp_path / "20251105.parquet", index=False)

    enriched = enrich_panel(
        {"CNStock:600519.SH": frame, "USStock:AAPL": frame.copy()},
        [
            {"key": "CNStock:600519.SH", "market": "CNStock", "symbol": "600519"},
            {"key": "USStock:AAPL", "market": "USStock", "symbol": "AAPL"},
        ],
        directory=tmp_path,
    )
    china = enriched["CNStock:600519.SH"]
    assert list(china["l2_obi"]) == pytest.approx([0.2, np.nan, 0.8], nan_ok=True)
    assert "l2_obi" not in enriched["USStock:AAPL"].columns
    assert compute_factor("l2_obi", china) == pytest.approx(0.8)
    assert np.isnan(compute_factor("l2_spread", china))


def test_factor_reads_unregistered_level2_column_without_talib():
    frame = _daily_frame()
    frame["l2_custom_flow"] = np.linspace(0.1, 0.8, len(frame))
    code = """
def initialize(context):
    context.set_universe(["CNStock:600519.SH"])
    context.subscribe(frequency="1d")

def handle_data(context, data):
    context.log("flow=%.2f" % factor("l2_custom_flow", "600519.SH"))
"""
    result = StrategyV2BacktestRunner(
        code=code,
        frames={"CNStock:600519.SH": frame},
        initial_capital=10000,
    ).run()
    assert result["logs"][-1] == "flow=0.80"


def test_level2_catalog_is_registered_with_display_keys():
    factors = list_factors(category="level2")
    ids = {item["factor_id"] for item in factors}
    assert "l2_active_net_buy_mean_20" in ids
    assert "l2_rv" in ids
    assert all(item["factor_type"] == "level2" for item in factors)
    assert len(factors) == 16 * (1 + 3 * 3)


def test_daily_backtest_attaches_level2_panel_without_fundamental_flag():
    calls = []

    def enrich(frames, members):
        calls.append(members)
        output = {}
        for key, frame in frames.items():
            output[key] = frame.assign(l2_active_net_buy=0.42)
        return output

    code = """
def initialize(context):
    context.set_universe(["CNStock:600519.SH"])
    context.subscribe(frequency="1d")

def handle_data(context, data):
    context.log("net=%.2f" % factor("l2_active_net_buy"))
"""
    service = StrategyV2BacktestService(
        repository=_Repository(),
        frame_fetcher=lambda *_args, **_kwargs: _daily_frame(),
        level2_enricher=enrich,
    )
    _, result = service.run(
        user_id=1,
        code=code,
        start_date=datetime(2025, 11, 3),
        end_date=datetime(2025, 11, 10, 23, 59),
        initial_capital=10000,
        persist=False,
    )
    assert calls
    assert result["logs"][-1] == "net=0.42"


def test_minute_backtest_does_not_attach_level2_panel():
    calls = []

    def enrich(frames, members):
        calls.append(True)
        return frames

    index = pd.date_range("2025-11-03 01:30", periods=30, freq="min")
    close = np.linspace(10, 11, len(index))
    frame = pd.DataFrame({
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": np.full(len(index), 100.0),
    }, index=index)
    code = """
def initialize(context):
    context.set_universe(["CNStock:600519.SH"])
    context.subscribe(frequency="1m")

def handle_data(context, data):
    pass
"""
    StrategyV2BacktestService(
        repository=_Repository(),
        frame_fetcher=lambda *_args, **_kwargs: frame,
        level2_enricher=enrich,
    ).run(
        user_id=1,
        code=code,
        start_date=datetime(2025, 11, 3, 1, 30),
        end_date=datetime(2025, 11, 3, 2, 30),
        initial_capital=10000,
        persist=False,
    )
    assert calls == []


def test_factor_research_receives_level2_column_without_fundamentals():
    calls = []

    def enrich(frames, members):
        calls.append(True)
        output = {}
        for index, (key, frame) in enumerate(frames.items()):
            # 截面差异，避免研究路径因为整列相同而失败。
            output[key] = frame.assign(l2_obi=float(index) + frame["close"] * 0)
        return output

    code = """
def initialize(context):
    context.set_universe(["CNStock:600519.SH", "CNStock:000001.SZ", "CNStock:300750.SZ"])
    context.subscribe(frequency="1d")

def on_rebalance(context, panel):
    pass
"""
    service = StrategyV2BacktestService(
        repository=_Repository(),
        frame_fetcher=lambda *_args, **_kwargs: _daily_frame(30, "2025-11-03"),
        level2_enricher=enrich,
    )
    result = service.research_factor(
        user_id=1,
        code=code,
        start_date=datetime(2025, 11, 3),
        end_date=datetime(2025, 12, 2, 23, 59),
        factor_id="l2_obi",
        groups=3,
        holding_period=1,
    )
    assert calls
    assert result["factorId"] == "l2_obi"


def _write_obi(directory, dates: list[str], rows: list[tuple[str, float]]) -> None:
    """每个交易日一个宽表，只放基础列 ``l2_obi``。"""
    for date in dates:
        frame = pd.DataFrame({
            "trade_date": [date] * len(rows),
            "symbol": [symbol for symbol, _value in rows],
            "l2_obi": [value for _symbol, value in rows],
        })
        frame.to_parquet(directory / f"{date}.parquet", index=False)


def test_rollups_are_computed_when_one_symbol_is_read(tmp_path):
    """一只股票没有镜像时，从按日文件现算 5 日均值，文件里不需要存滚动列。"""
    clear_panel_cache()
    dates = ["20251103", "20251104", "20251105", "20251106", "20251107"]
    for index, date in enumerate(dates):
        _write_obi(tmp_path, [date], [("600519.SH", float(index + 1))])
    index = pd.to_datetime(["2025-11-03", "2025-11-04", "2025-11-05", "2025-11-06", "2025-11-07"])
    frame = _daily_frame(5, "2025-11-03")
    frame.index = index
    enriched = enrich_panel(
        {"CNStock:600519.SH": frame},
        [{"key": "CNStock:600519.SH", "market": "CNStock", "symbol": "600519.SH"}],
        directory=tmp_path,
    )
    means = enriched["CNStock:600519.SH"]["l2_obi_mean_5"].tolist()
    assert np.isnan(means[0])
    assert means[-1] == pytest.approx(3.0)


def test_single_symbol_uses_mirror_and_a_later_daily_file(tmp_path):
    """镜像停在上周时，这一周的新交易日从按日宽表补上后再算均值。"""
    clear_panel_cache()
    dates = ["20251103", "20251104", "20251105", "20251106", "20251107"]
    mirror = pd.DataFrame({
        "trade_date": dates[:4],
        "symbol": ["600519.SH"] * 4,
        "l2_obi": [1.0, 2.0, 3.0, 4.0],
    })
    symbol_dir = tmp_path / "symbol"
    symbol_dir.mkdir()
    mirror.to_parquet(symbol_dir / "600519.SH.parquet", index=False)
    _write_obi(tmp_path, [dates[-1]], [("600519.SH", 5.0), ("000001.SZ", 9.0)])
    index = pd.to_datetime(["2025-11-07"])
    frame = _daily_frame(1, "2025-11-07")
    frame.index = index
    enriched = enrich_panel(
        {"CNStock:600519.SH": frame},
        [{"key": "CNStock:600519.SH", "market": "CNStock", "symbol": "600519.SH"}],
        directory=tmp_path,
    )
    assert enriched["CNStock:600519.SH"]["l2_obi_mean_5"].iloc[0] == pytest.approx(3.0)


def test_portfolio_reads_daily_files_not_the_symbol_mirror(tmp_path):
    """组合回测用按日宽表。镜像里的过期数值不能盖过当天截面。"""
    clear_panel_cache()
    dates = ["20251103", "20251104", "20251105", "20251106", "20251107"]
    for index, date in enumerate(dates):
        _write_obi(
            tmp_path,
            [date],
            [("600519.SH", float(index + 1)), ("000001.SZ", float(index + 1))],
        )
    stale = pd.DataFrame({
        "trade_date": dates,
        "symbol": ["600519.SH"] * 5,
        "l2_obi": [0.0] * 5,
    })
    symbol_dir = tmp_path / "symbol"
    symbol_dir.mkdir()
    stale.to_parquet(symbol_dir / "600519.SH.parquet", index=False)
    index = pd.to_datetime(dates, format="%Y%m%d")
    frame = _daily_frame(5, "2025-11-03")
    frame.index = index
    members = [
        {"key": "CNStock:600519.SH", "market": "CNStock", "symbol": "600519.SH"},
        {"key": "CNStock:000001.SZ", "market": "CNStock", "symbol": "000001.SZ"},
    ]
    enriched = enrich_panel(
        {"CNStock:600519.SH": frame, "CNStock:000001.SZ": frame.copy()},
        members,
        directory=tmp_path,
    )
    assert enriched["CNStock:600519.SH"]["l2_obi"].iloc[-1] == pytest.approx(5.0)
    assert enriched["CNStock:600519.SH"]["l2_obi_mean_5"].iloc[-1] == pytest.approx(3.0)
    assert enriched["CNStock:000001.SZ"]["l2_obi_mean_5"].iloc[-1] == pytest.approx(3.0)
