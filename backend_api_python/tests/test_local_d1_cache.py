"""本地 SQLite 读缓存：命中跳过 D1、回写与容量/天数淘汰。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def cache_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """每个用例独立 SQLite 文件，避免污染本机缓存。"""
    from app.services.level2_factors import local_d1_cache

    path = tmp_path / "level2_d1_cache.sqlite"
    monkeypatch.setenv("LEVEL2_D1_CACHE_PATH", str(path))
    local_d1_cache.reset_for_tests()
    yield path
    local_d1_cache.reset_for_tests()


def test_factor_cache_defaults_cover_three_years():
    """默认天数与体积足以覆盖单股约三年。"""
    from app.services.level2_factors.factor_cache import factor_limit_bytes, factor_max_days

    assert factor_max_days() >= 1100
    assert factor_limit_bytes() >= 2048 * 1024 * 1024


def test_local_cache_hit_skips_d1(cache_db, monkeypatch: pytest.MonkeyPatch):
    """本地已有行时 enrich 不再调用 D1 fetch。"""
    from app.services.level2_factor_panel import clear_panel_cache, enrich_panel
    from app.services.level2_factors import d1_client, d1_factors, local_d1_cache

    clear_panel_cache()
    local_d1_cache.upsert_rows([{
        "trade_date": "20260929",
        "symbol": "002074.SZ",
        "l2_active_net_buy": 0.42,
    }])
    calls: list[tuple] = []

    def boom(symbols, dates):
        calls.append((list(symbols), list(dates)))
        raise AssertionError("should not hit D1")

    monkeypatch.setattr(d1_client, "configured", lambda: True)
    monkeypatch.setattr(d1_factors, "fetch_symbols", boom)
    monkeypatch.setattr(d1_factors, "warmup_dates", lambda *a, **k: [])
    monkeypatch.setattr(local_d1_cache, "warmup_dates", lambda *a, **k: [])

    index = pd.to_datetime(["2026-09-29"])
    frame = pd.DataFrame({
        "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0],
    }, index=index)
    members = [{"key": "CNStock:002074.SZ", "market": "CNStock", "symbol": "002074"}]
    try:
        enriched = enrich_panel({"CNStock:002074.SZ": frame}, members)
        assert calls == []
        assert enriched["CNStock:002074.SZ"]["l2_active_net_buy"].iloc[0] == pytest.approx(0.42)
    finally:
        clear_panel_cache()


def test_local_cache_miss_fetches_d1_and_writes_back(cache_db, monkeypatch: pytest.MonkeyPatch):
    """缺口走 D1，回写后第二次命中本地。"""
    from app.services.level2_factor_panel import clear_panel_cache, enrich_panel
    from app.services.level2_factors import d1_client, d1_factors, local_d1_cache

    clear_panel_cache()
    calls: list[int] = []

    def fetch_symbols(symbols, dates):
        calls.append(1)
        return [{
            "trade_date": "20260929",
            "symbol": "002074.SZ",
            "l2_active_net_buy": 0.9,
        }]

    monkeypatch.setattr(d1_client, "configured", lambda: True)
    monkeypatch.setattr(d1_factors, "fetch_symbols", fetch_symbols)
    monkeypatch.setattr(d1_factors, "warmup_dates", lambda *a, **k: [])
    monkeypatch.setattr(local_d1_cache, "warmup_dates", lambda *a, **k: [])

    index = pd.to_datetime(["2026-09-29"])
    frame = pd.DataFrame({
        "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0],
    }, index=index)
    members = [{"key": "CNStock:002074.SZ", "market": "CNStock", "symbol": "002074"}]
    try:
        first = enrich_panel({"CNStock:002074.SZ": frame}, members)
        assert len(calls) == 1
        assert first["CNStock:002074.SZ"]["l2_active_net_buy"].iloc[0] == pytest.approx(0.9)
        cached = local_d1_cache.fetch(["002074.SZ"], ["20260929"])
        assert cached and cached[0]["l2_active_net_buy"] == pytest.approx(0.9)

        clear_panel_cache()
        second = enrich_panel({"CNStock:002074.SZ": frame}, members)
        assert len(calls) == 1
        assert second["CNStock:002074.SZ"]["l2_active_net_buy"].iloc[0] == pytest.approx(0.9)
    finally:
        clear_panel_cache()


def test_local_cache_evicts_by_max_days(cache_db, monkeypatch: pytest.MonkeyPatch):
    """超过 MAX_DAYS 的交易日被删掉。"""
    from app.services.level2_factors import local_d1_cache

    monkeypatch.setenv("LEVEL2_FACTOR_CACHE_MAX_DAYS", "180")
    monkeypatch.setenv("LEVEL2_FACTOR_CACHE_MAX_MB", "2048")
    local_d1_cache.upsert_rows([
        {"trade_date": "20200101", "symbol": "002074.SZ", "l2_spread": 0.1},
        {"trade_date": "20260922", "symbol": "002074.SZ", "l2_spread": 0.2},
    ])
    rows = local_d1_cache.fetch(["002074.SZ"], ["20200101", "20260922"])
    dates = {str(row["trade_date"]) for row in rows}
    assert "20200101" not in dates
    assert "20260922" in dates


def test_local_cache_evicts_by_max_mb(cache_db, monkeypatch: pytest.MonkeyPatch):
    """超容量时删最老交易日，保留 keep 日。"""
    from app.services.level2_factors import local_d1_cache

    monkeypatch.setenv("LEVEL2_FACTOR_CACHE_MAX_DAYS", "0")
    monkeypatch.setenv("LEVEL2_FACTOR_CACHE_MAX_MB", "0.00001")
    local_d1_cache.upsert_rows([
        {"trade_date": "20260921", "symbol": "002074.SZ", "l2_spread": 0.1},
    ])
    local_d1_cache.upsert_rows([
        {"trade_date": "20260922", "symbol": "002074.SZ", "l2_spread": 0.2},
    ])
    rows = local_d1_cache.fetch(["002074.SZ"], ["20260921", "20260922"])
    dates = {str(row["trade_date"]) for row in rows}
    assert "20260921" not in dates
    assert "20260922" in dates


def test_three_year_span_kept_under_default_days(cache_db, monkeypatch: pytest.MonkeyPatch):
    """默认 MAX_DAYS 下，约三年前的交易日仍保留。"""
    from app.services.level2_factors import local_d1_cache
    from app.services.level2_factors.factor_cache import factor_max_days

    monkeypatch.delenv("LEVEL2_FACTOR_CACHE_MAX_DAYS", raising=False)
    monkeypatch.delenv("LEVEL2_FACTOR_CACHE_MAX_MB", raising=False)
    assert factor_max_days() >= 1100
    # 相对「今天」约 1000 天前的固定日；在默认 1200 内应留下。
    local_d1_cache.upsert_rows([
        {"trade_date": "20240102", "symbol": "002074.SZ", "l2_spread": 0.1},
        {"trade_date": "20260922", "symbol": "002074.SZ", "l2_spread": 0.2},
    ])
    rows = local_d1_cache.fetch(["002074.SZ"], ["20240102", "20260922"])
    dates = {str(row["trade_date"]) for row in rows}
    assert dates == {"20240102", "20260922"}
