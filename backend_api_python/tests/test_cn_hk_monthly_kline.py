"""A 股/港股月线：1M 不能覆盖 1 分钟，且只在前置数据源失败后才走 AkShare。"""

from app.data_sources.asia_stock_kline import normalize_chart_timeframe
from app.data_sources.cn_stock import CNStockDataSource
from app.data_sources.hk_stock import HKStockDataSource
from app.services.backtest_limits import (
    backtest_range_policy,
    backtest_warmup_calendar_days,
    normalize_backtest_timeframe,
)
from app.services.strategy_v2 import compile_strategy_v2
from app.services.strategy_v2.frequencies import frequency_seconds, normalize_frequency
from app.services.strategy_v2.runtime import _is_intraday_frequency, _periods_per_year
from app.services.strategy_v2.service import _warmup_calendar_days
from app.services.strategy_runtime.timeframes import live_history_days


_BAR = {"time": 1704067200, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0}


def test_chart_monthly_alias_does_not_replace_one_minute():
    assert normalize_chart_timeframe("1m") == "1m"
    assert normalize_chart_timeframe("1M") == "1M"
    assert normalize_chart_timeframe("1mo") == "1M"
    assert normalize_chart_timeframe("month") == "1M"
    assert normalize_chart_timeframe("monthly") == "1M"


def test_strategy_monthly_alias_does_not_replace_one_minute():
    assert normalize_frequency("1m") == "1m"
    assert normalize_frequency("1M") == "1mo"
    assert normalize_frequency("monthly") == "1mo"
    assert frequency_seconds("1M") == 2_592_000
    assert frequency_seconds("1m") == 60


def test_backtest_monthly_limit_matches_daily_and_skips_minute_warmup():
    assert normalize_backtest_timeframe("1m") == "1m"
    assert normalize_backtest_timeframe("1M") == "1M"
    assert normalize_backtest_timeframe("1mo") == "1M"
    assert backtest_range_policy("CNStock", "1M").max_days == backtest_range_policy("CNStock", "1D").max_days
    assert backtest_warmup_calendar_days("1m", 2) == 1
    assert backtest_warmup_calendar_days("1M", 2) >= 31
    assert _warmup_calendar_days("1mo", 12, candidates=[{"market": "CNStock"}]) >= 31


def test_monthly_is_not_treated_as_a_one_minute_bar():
    assert _is_intraday_frequency("1m") is True
    assert _is_intraday_frequency("1M") is False
    assert _is_intraday_frequency("1mo") is False
    assert _periods_per_year("1M", ["CNStock"]) == 12.0
    assert _periods_per_year("1m", ["CNStock"]) > 12.0
    assert live_history_days("1mo", 12, [{"market": "CNStock"}]) >= 30


def test_compiled_strategy_accepts_chart_monthly_token():
    code = """
def initialize(context):
    context.set_universe(["CNStock:600519"])
    context.subscribe(frequency="1M")

def handle_data(context, data):
    return
"""
    compiled = compile_strategy_v2(code)
    assert compiled.manifest.subscriptions[0].frequency == "1mo"


def test_cn_monthly_uses_tencent_before_akshare(monkeypatch):
    import app.data_sources.cn_stock as cn

    periods = []
    monkeypatch.setattr(cn, "fetch_twelvedata_klines", lambda **kwargs: [])
    monkeypatch.setattr(cn, "fetch_kline", lambda code, period, count=300, adj="qfq", timeout=10: periods.append(period) or [["2024-01-02", "10", "11", "12", "9", "1000"]])
    monkeypatch.setattr(cn, "fetch_yfinance_klines", lambda **kwargs: (_ for _ in ()).throw(AssertionError("yfinance should not run")))
    monkeypatch.setattr(cn, "fetch_akshare_weekly_klines", lambda **kwargs: (_ for _ in ()).throw(AssertionError("akshare should not run")))

    rows = CNStockDataSource().get_kline("600519", "1M", 5)

    assert periods == ["month"]
    assert rows and rows[0]["close"] == 11.0


def test_cn_monthly_falls_back_to_akshare_monthly(monkeypatch):
    import app.data_sources.cn_stock as cn

    seen = {}

    def _ak(**kwargs):
        seen.update(kwargs)
        return [_BAR]

    monkeypatch.setattr(cn, "fetch_twelvedata_klines", lambda **kwargs: [])
    monkeypatch.setattr(cn, "fetch_kline", lambda *args, **kwargs: [])
    monkeypatch.setattr(cn, "fetch_yfinance_klines", lambda **kwargs: [])
    monkeypatch.setattr(cn, "fetch_akshare_weekly_klines", _ak)

    rows = CNStockDataSource().get_kline("600519", "monthly", 8)

    assert seen["is_hk"] is False
    assert seen["period"] == "monthly"
    assert rows == [_BAR]


def test_hk_monthly_uses_tencent_month(monkeypatch):
    import app.data_sources.hk_stock as hk

    periods = []
    monkeypatch.setattr(hk, "fetch_twelvedata_klines", lambda **kwargs: [])
    monkeypatch.setattr(hk, "fetch_kline", lambda code, period, count=300, adj="qfq", timeout=10: periods.append((code, period)) or [["2024-01-02", "10", "11", "12", "9", "1000"]])
    monkeypatch.setattr(hk, "fetch_akshare_weekly_klines", lambda **kwargs: (_ for _ in ()).throw(AssertionError("akshare should not run")))

    rows = HKStockDataSource().get_kline("00700", "1M", 5)

    assert periods[0][1] == "month"
    assert rows
