"""因子副图序列：长度对齐 K 线，历史不足为空，Level2 不向前填充。"""
from __future__ import annotations

import pandas as pd
import pytest

from app.services.factors.registry import compute_factor
from app.services.factors.series import bars_to_frame, build_factor_plot
from app.services.level2_factor_panel import clear_panel_cache


def _bars(count: int, start_ms: int = 1_730_592_000_000, step_ms: int = 86_400_000) -> list[dict]:
    bars = []
    price = 10.0
    for index in range(count):
        bars.append({
            "time": start_ms + index * step_ms,
            "open": price,
            "high": price + 0.4,
            "low": price - 0.4,
            "close": price + 0.2,
            "volume": 1000,
        })
        price += 0.2
    return bars


def test_momentum_series_matches_visible_history_and_warmup_is_null():
    bars = _bars(6)
    frame = bars_to_frame(bars)
    payload = build_factor_plot("momentum", frame, params={"period": 2})
    data = payload["plots"][0]["data"]
    assert len(data) == len(frame)
    assert data[0] is None
    assert data[1] is None
    assert data[-1] == pytest.approx(compute_factor("momentum", frame, {"period": 2}))
    assert payload["plots"][0]["overlay"] is False


def test_level2_series_joins_the_session_without_forward_fill(tmp_path, monkeypatch):
    clear_panel_cache()
    pd.DataFrame([{
        "trade_date": "20251104",
        "symbol": "600519.SH",
        "l2_spread": 0.02,
    }]).to_parquet(tmp_path / "20251104.parquet", index=False)
    from app.services.level2_factor_panel import enrich_panel

    def enricher(frames, members=None):
        return enrich_panel(frames, members, directory=tmp_path)

    # 上海 11-03 / 11-04 / 11-05 的 UTC 午夜，中间那天才有面板。
    start = int(pd.Timestamp("2025-11-03", tz="UTC").timestamp() * 1000)
    payload = build_factor_plot(
        "l2_spread",
        bars_to_frame(_bars(3, start_ms=start)),
        market="CNStock",
        symbol="600519",
        timeframe="1d",
        level2_enricher=enricher,
        level2_filler=lambda *_args: False,
    )
    assert payload["plots"][0]["data"][0] is None
    assert payload["plots"][0]["data"][1] == pytest.approx(0.02)
    assert payload["plots"][0]["data"][2] is None
    assert payload["notice_key"] is None


def test_level2_series_matches_shanghai_local_midnight(tmp_path, monkeypatch):
    """腾讯日线是上海当地午夜。图表改写之前的这个时间必须对上同一交易日。"""
    clear_panel_cache()
    pd.DataFrame([{
        "trade_date": "20251104",
        "symbol": "600519.SH",
        "l2_active_net_buy": 0.15,
    }]).to_parquet(tmp_path / "20251104.parquet", index=False)
    from app.services.level2_factor_panel import enrich_panel

    def enricher(frames, members=None):
        return enrich_panel(frames, members, directory=tmp_path)

    # 11-04 00:00 上海 = 11-03 16:00 UTC。前后两个当地午夜没有面板。
    start = int(pd.Timestamp("2025-11-03", tz="Asia/Shanghai").timestamp() * 1000)
    payload = build_factor_plot(
        "l2_active_net_buy",
        bars_to_frame(_bars(3, start_ms=start)),
        market="CNStock",
        symbol="SH600519",
        timeframe="1D",
        level2_enricher=enricher,
        level2_filler=lambda *_args: False,
    )
    data = payload["plots"][0]["data"]
    assert data[0] is None
    assert data[1]["value"] == pytest.approx(0.15)
    assert data[1]["color"] == "#22C55E"
    assert data[2] is None
    assert payload["notice_key"] is None


def test_level2_series_repeats_the_same_session_on_duplicate_bars(tmp_path, monkeypatch):
    """同一上海交易日的两根 K 线都取到当日因子，不能因重复日期把接口打成 500。"""
    clear_panel_cache()
    pd.DataFrame([{
        "trade_date": "20251104",
        "symbol": "600519.SH",
        "l2_spread": 0.02,
    }]).to_parquet(tmp_path / "20251104.parquet", index=False)
    from app.services.level2_factor_panel import enrich_panel

    def enricher(frames, members=None):
        return enrich_panel(frames, members, directory=tmp_path)

    same_day = int(pd.Timestamp("2025-11-04", tz="UTC").timestamp() * 1000)
    earlier = int(pd.Timestamp("2025-11-03 16:00", tz="UTC").timestamp() * 1000)
    payload = build_factor_plot(
        "l2_spread",
        bars_to_frame([
            {"time": earlier, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1},
            {"time": same_day, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1},
        ]),
        market="CNStock",
        symbol="600519.SH",
        timeframe="1d",
        level2_enricher=enricher,
        level2_filler=lambda *_args: False,
    )
    assert payload["plots"][0]["data"] == pytest.approx([0.02, 0.02])


def test_missing_level2_symbol_does_not_auto_fill():
    """缺数默认只展示空点 + 面板说明，不自动后台补算。"""
    start = int(pd.Timestamp("2026-06-01", tz="Asia/Shanghai").timestamp() * 1000)
    payload = build_factor_plot(
        "l2_active_net_buy",
        bars_to_frame(_bars(2, start_ms=start)),
        market="CNStock",
        symbol="002074",
        timeframe="1D",
        level2_enricher=lambda frames, _members: frames,
    )
    assert payload["notice_key"] == "factorLibrary.level2PanelNotice"
    assert all(item is None for item in payload["plots"][0]["data"])


def test_explicit_level2_filler_still_reports_fetching():
    """显式注入 filler 时保留旧补数语义（测试/兼容）。"""
    seen: list[tuple[str, tuple[str, ...]]] = []

    def filler(symbol, dates):
        seen.append((symbol, tuple(dates)))
        return True

    start = int(pd.Timestamp("2026-06-01", tz="Asia/Shanghai").timestamp() * 1000)
    payload = build_factor_plot(
        "l2_active_net_buy",
        bars_to_frame(_bars(2, start_ms=start)),
        market="CNStock",
        symbol="002074",
        timeframe="1D",
        level2_enricher=lambda frames, _members: frames,
        level2_filler=filler,
    )
    assert payload["notice_key"] == "factorLibrary.level2Fetching"
    assert seen[0][0] == "002074"
    assert seen[0][1] == ("20260601", "20260602")


def test_partial_level2_values_show_without_auto_fill():
    """已有部分点时只展示已有数据，默认不触发后台补数。"""
    def enrich(frames, _members):
        key = next(iter(frames))
        frame = frames[key].copy()
        frame["l2_active_net_buy"] = [0.2, None]
        return {key: frame}

    start = int(pd.Timestamp("2026-06-01", tz="Asia/Shanghai").timestamp() * 1000)
    payload = build_factor_plot(
        "l2_active_net_buy",
        bars_to_frame(_bars(2, start_ms=start)),
        market="CNStock",
        symbol="002074",
        timeframe="1D",
        level2_enricher=enrich,
    )
    assert payload["notice_key"] is None
    assert payload["plots"][0]["data"][0]["value"] == pytest.approx(0.2)
    assert payload["plots"][0]["data"][1] is None


def test_level2_series_uses_cache_before_the_panel():
    """临时表里有的日期盖过面板，没有的日期仍用面板。"""
    from app.services.level2_factors.factor_cache import MemoryFactorCache

    def enrich(frames, _members):
        key = next(iter(frames))
        frame = frames[key].copy()
        frame["l2_active_net_buy"] = [0.01, 0.02]
        return {key: frame}

    cache = MemoryFactorCache()
    cache.upsert("600519.SH", "20260602", {"l2_active_net_buy": 0.5})
    start = int(pd.Timestamp("2026-06-01", tz="Asia/Shanghai").timestamp() * 1000)
    payload = build_factor_plot(
        "l2_active_net_buy",
        bars_to_frame(_bars(2, start_ms=start)),
        market="CNStock",
        symbol="600519",
        timeframe="1D",
        level2_enricher=enrich,
        level2_cache=cache,
    )
    data = payload["plots"][0]["data"]
    assert data[0]["value"] == pytest.approx(0.01)
    assert data[1]["value"] == pytest.approx(0.5)


def test_signed_level2_factor_uses_histogram_and_spread_stays_a_line():
    """主动净买入率绕着 0，用红绿柱；价差和标准差仍是折线。"""

    def enrich(frames, _members):
        key = next(iter(frames))
        frame = frames[key].copy()
        frame["l2_active_net_buy"] = [0.2, -0.1, None]
        frame["l2_active_net_buy_std_20"] = [0.05, 0.06, 0.07]
        frame["l2_spread"] = [0.01, 0.02, 0.03]
        return {key: frame}

    bars = bars_to_frame(_bars(3))
    common = {"market": "CNStock", "symbol": "600519", "timeframe": "1d", "level2_enricher": enrich}
    buy = build_factor_plot("l2_active_net_buy", bars, **common)["plots"][0]
    assert buy["type"] == "histogram"
    assert buy["data"][0] == {"value": pytest.approx(0.2), "color": "#22C55E"}
    assert buy["data"][1]["color"] == "#EF4444"
    assert buy["data"][1]["value"] == pytest.approx(-0.1)
    assert buy["data"][2] is None
    spread = build_factor_plot("l2_spread", bars, **common)["plots"][0]
    assert spread["type"] == "line"
    assert spread["data"][0] == pytest.approx(0.01)
    deviation = build_factor_plot("l2_active_net_buy_std_20", bars, **common)["plots"][0]
    assert deviation["type"] == "line"


def test_level2_series_on_intraday_bars_stays_empty():
    payload = build_factor_plot(
        "l2_spread",
        bars_to_frame(_bars(3, step_ms=60_000)),
        market="CNStock",
        symbol="600519.SH",
        timeframe="1m",
    )
    assert payload["plots"][0]["data"] == [None, None, None]
    assert payload["notice_key"] == "factorLibrary.level2PanelNotice"


def test_fundamental_series_uses_injected_point_in_time_columns():
    def enrich(frame):
        enriched = frame.copy()
        enriched["market_cap"] = [None, 10.0, 12.0]
        return enriched

    payload = build_factor_plot(
        "market_cap",
        bars_to_frame(_bars(3)),
        market="USStock",
        symbol="AAPL",
        timeframe="1d",
        fundamental_enricher=enrich,
    )
    assert payload["plots"][0]["data"][0] is None
    assert payload["plots"][0]["data"][1] == pytest.approx(10.0)
    assert payload["plots"][0]["data"][2] == pytest.approx(12.0)
