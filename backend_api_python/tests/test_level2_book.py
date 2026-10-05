"""明细只从 Parquet 读入，并可以算出一天的因子文件。"""
from pathlib import Path

import pandas as pd
import pytest

from app.services.level2_factors.book import load_book, load_frame, parquet_directory
from app.services.level2_factors.build import write_trade_date


@pytest.fixture(autouse=True)
def _hide_host_staging(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """测试不要读到本机 staging，避免把真实明细当成下载结果。"""
    monkeypatch.setenv("LEVEL2_STAGING_PARQUET_DIR", str(tmp_path_factory.mktemp("no-staging")))


@pytest.fixture
def disable_d1(monkeypatch: pytest.MonkeyPatch) -> None:
    """需要本地日 parquet 的用例关掉 Worker，避免读到本机 .env 去连网。"""
    from app.services.level2_factors import d1_client

    monkeypatch.setattr(d1_client, "configured", lambda: False)


def _write_book(root: Path, date: str, code: str) -> None:
    day = root / date / code
    day.mkdir(parents=True)
    snap = pd.DataFrame([{
        "时间": "100000000",
        "开盘价": 100000.0,
        "成交价": 101000.0,
        "前收盘": 99000.0,
        "申买价1": 100000.0,
        "申卖价1": 101000.0,
        "叫买总量": 300.0,
        "叫卖总量": 100.0,
        **{f"申买量{level}": 10.0 for level in range(1, 11)},
        **{f"申卖量{level}": 20.0 for level in range(1, 11)},
    }])
    trades = pd.DataFrame([{
        "时间": "100000000",
        "成交代码": "",
        "成交价格": 100000,
        "成交数量": 100,
        "BS标志": "B",
        "叫买序号": "1",
        "叫卖序号": "2",
    }])
    orders = pd.DataFrame(columns=["时间", "委托类型", "委托代码", "交易所委托号", "委托数量"])
    snap.to_parquet(day / "行情.parquet", index=False)
    trades.to_parquet(day / "逐笔成交.parquet", index=False)
    orders.to_parquet(day / "逐笔委托.parquet", index=False)
    # 旁边放一份 CSV，读取逻辑也不应该打开它。
    (day / "行情.csv").write_text("ignored", encoding="utf-8")


def test_load_book_reads_parquet_only(tmp_path: Path):
    _write_book(tmp_path, "20251103", "600000.SH")
    frames = load_book(tmp_path, "20251103", "600000.SH")
    assert len(frames["行情"]) == 1
    assert frames["逐笔成交"].iloc[0]["BS标志"] == "B"
    with pytest.raises(FileNotFoundError):
        load_frame(tmp_path, "20251103", "600000.SH", "行情.csv")


def test_build_writes_factor_panel_from_parquet(tmp_path: Path, disable_d1):
    books = tmp_path / "books"
    output = tmp_path / "factors"
    _write_book(books, "20251103", "600000.SH")
    path = write_trade_date("20251103", books, output, codes=["600000.SH"])
    assert path is not None and path.exists()
    panel = pd.read_parquet(path)
    assert panel.iloc[0]["symbol"] == "600000.SH"
    assert panel.iloc[0]["l2_spread"] > 0
    assert "l2_spread_mean_5" not in panel.columns
    assert (output / "_done" / "20251103.json").is_file()


def _parquet_bytes(frame: pd.DataFrame) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    frame.to_parquet(buffer, index=False)
    return buffer.getvalue()


def _quote_bytes() -> bytes:
    return _parquet_bytes(pd.DataFrame([{
        "时间": "100000000",
        "开盘价": 100000.0,
        "成交价": 101000.0,
        "前收盘": 99000.0,
        "申买价1": 100000.0,
        "申卖价1": 101000.0,
        "叫买总量": 300.0,
        "叫卖总量": 100.0,
        **{f"申买量{level}": 10.0 for level in range(1, 11)},
        **{f"申卖量{level}": 20.0 for level in range(1, 11)},
    }]))


def test_missing_book_is_downloaded_once(tmp_path: Path):
    from app.services.level2_factors.book import set_book_downloader

    calls: list[tuple[str, str, str]] = []
    payload = _quote_bytes()

    def fake(date: str, code: str, ftype: str) -> bytes | None:
        calls.append((date, code, ftype))
        return payload if ftype == "行情" else None

    set_book_downloader(fake)
    try:
        frame = load_frame(tmp_path, "20260601", "601328.SH", "行情")
        assert len(frame) == 1
        assert (tmp_path / "20260601" / "601328.SH" / "行情.parquet").is_file()
        load_frame(tmp_path, "20260601", "601328.SH", "行情")
        assert calls == [("20260601", "601328.SH", "行情")]
    finally:
        set_book_downloader(None)


def test_empty_local_day_uses_remote_codes(tmp_path: Path, disable_d1):
    from app.services.level2_factors.book import set_book_downloader, set_remote_lister

    books = tmp_path / "books"
    books.mkdir()
    payload = {
        "行情": _quote_bytes(),
        "逐笔成交": _parquet_bytes(pd.DataFrame([{
            "时间": "100000000",
            "成交代码": "",
            "成交价格": 100000,
            "成交数量": 100,
            "BS标志": "B",
            "叫买序号": "1",
            "叫卖序号": "2",
        }])),
        "逐笔委托": _parquet_bytes(pd.DataFrame(columns=["时间", "委托类型", "委托代码", "交易所委托号", "委托数量"])),
    }

    def fake(date: str, code: str, ftype: str) -> bytes | None:
        return payload[ftype]

    set_remote_lister(lambda date: ["600000.SH"] if date == "20260601" else [])
    set_book_downloader(fake)
    try:
        path = write_trade_date("20260601", books, tmp_path / "factors")
        assert path is not None
        panel = pd.read_parquet(path)
        assert panel.iloc[0]["symbol"] == "600000.SH"
        assert (books / "20260601" / "600000.SH" / "行情.parquet").is_file()
    finally:
        set_remote_lister(None)
        set_book_downloader(None)


def test_cache_drops_the_oldest_date_and_keeps_the_current_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.services.level2_factors.book import set_book_downloader

    monkeypatch.setenv("LEVEL2_PARQUET_CACHE_MAX_GB", "0.000001")
    old = tmp_path / "20260601" / "601328.SH"
    old.mkdir(parents=True)
    (old / "行情.parquet").write_bytes(b"x" * 4000)

    payload = _quote_bytes()

    def fake(date: str, code: str, ftype: str) -> bytes | None:
        return payload

    set_book_downloader(fake)
    try:
        load_frame(tmp_path, "20260602", "601328.SH", "行情")
        assert not (tmp_path / "20260601").exists()
        assert (tmp_path / "20260602" / "601328.SH" / "行情.parquet").is_file()
        load_frame(tmp_path, "20260602", "601328.SH", "逐笔成交")
        assert (tmp_path / "20260602").is_dir()
    finally:
        set_book_downloader(None)


def test_remote_book_path_inserts_year_and_month(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BAIDU_APP_NAME", "level2")
    monkeypatch.setenv("BAIDU_REMOTE_PREFIX", "l2")
    from app.services.level2_factors.baidu_books import remote_path

    assert remote_path("20260601", "601328.SH", "行情") == (
        "/apps/level2/l2/2026/202606/20260601/601328.SH/行情.parquet"
    )


def test_finished_day_still_fetches_a_new_symbol(tmp_path: Path, disable_d1):
    """日期已经给别的股票写过面板时，新标的仍要下载，并写入临时表。"""
    from app.services.level2_factors.book import set_book_downloader
    from app.services.level2_factors.build import ensure_symbol
    from app.services.level2_factors.factor_cache import MemoryFactorCache

    books = tmp_path / "books"
    output = tmp_path / "factors"
    _write_book(books, "20260601", "601328.SH")
    assert write_trade_date("20260601", books, output, codes=["601328.SH"]) is not None
    calls: list[tuple[str, str, str]] = []
    payload = {
        "行情": _quote_bytes(),
        "逐笔成交": _parquet_bytes(pd.DataFrame([{
            "时间": "100000000",
            "成交代码": "",
            "成交价格": 100000,
            "成交数量": 100,
            "BS标志": "B",
            "叫买序号": "1",
            "叫卖序号": "2",
        }])),
        "逐笔委托": _parquet_bytes(pd.DataFrame(columns=["时间", "委托类型", "委托代码", "交易所委托号", "委托数量"])),
    }

    def fake(date: str, code: str, ftype: str) -> bytes | None:
        calls.append((date, code, ftype))
        return payload[ftype]

    store = MemoryFactorCache()
    set_book_downloader(fake)
    try:
        ensure_symbol("002074.SZ", ["20260601"], parquet_dir=books, store=store)
        assert store.has("002074.SZ", "20260601")
        assert store.rows[("002074.SZ", "20260601")]["l2_spread"] is not None
        assert calls
        assert not (books / "20260601" / "002074.SZ").exists()
        calls.clear()
        ensure_symbol("002074.SZ", ["20260601"], parquet_dir=books, store=store)
        assert calls == []
    finally:
        set_book_downloader(None)


def test_default_parquet_directory_stays_in_quantdinger(monkeypatch: pytest.MonkeyPatch):
    """未配置时缓存落在项目 data 目录，不写到 level2 的 staging。"""
    monkeypatch.delenv("LEVEL2_PARQUET_DIR", raising=False)
    path = parquet_directory()
    assert path is not None
    assert path.parts[-2:] == ("data", "level2_parquet")
    assert ".staging" not in path.parts


def test_book_cache_drops_expired_dates_and_keeps_today(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """保留天数外的交易日删除，正在写入的日期留下。"""
    from app.services.level2_factors.book import enforce_book_cache

    monkeypatch.setenv("LEVEL2_PARQUET_CACHE_MAX_DAYS", "180")
    monkeypatch.setenv("LEVEL2_PARQUET_CACHE_MAX_GB", "10")
    old = tmp_path / "20200101" / "601328.SH"
    current = tmp_path / "20260922" / "601328.SH"
    old.mkdir(parents=True)
    current.mkdir(parents=True)
    (old / "行情.parquet").write_bytes(b"old")
    (current / "行情.parquet").write_bytes(b"now")
    enforce_book_cache(tmp_path, keep_date="20260922")
    assert not old.exists()
    assert current.is_dir()


def test_factor_cache_drops_old_dates_and_oversized_days(monkeypatch: pytest.MonkeyPatch):
    """临时表过期和超容量时删最老交易日，正在写入的那天留下。"""
    from app.services.level2_factors.factor_cache import MemoryFactorCache

    monkeypatch.setenv("LEVEL2_FACTOR_CACHE_MAX_DAYS", "180")
    monkeypatch.setenv("LEVEL2_FACTOR_CACHE_MAX_MB", "512")
    store = MemoryFactorCache()
    store.upsert("002074.SZ", "20200101", {"l2_spread": 0.1})
    store.upsert("002074.SZ", "20260922", {"l2_spread": 0.2})
    assert not store.has("002074.SZ", "20200101")
    assert store.has("002074.SZ", "20260922")

    monkeypatch.setenv("LEVEL2_FACTOR_CACHE_MAX_DAYS", "0")
    monkeypatch.setenv("LEVEL2_FACTOR_CACHE_MAX_MB", "0.00001")
    store = MemoryFactorCache()
    store.upsert("002074.SZ", "20260921", {"l2_spread": 0.1})
    store.upsert("002074.SZ", "20260922", {"l2_spread": 0.2})
    assert not store.has("002074.SZ", "20260921")
    assert store.has("002074.SZ", "20260922")


def test_recent_weekdays_cover_one_year_without_weekends():
    """近一年只含工作日，含今天、不含周六周日。"""
    from datetime import date

    from app.services.level2_factors.build import recent_weekdays

    dates = recent_weekdays(date(2026, 9, 30))
    assert dates[0] == "20250930"
    assert dates[-1] == "20260930"
    assert "20260926" not in dates
    assert "20260927" not in dates
    assert all(date(int(item[:4]), int(item[4:6]), int(item[6:])).weekday() < 5 for item in dates)


def test_symbol_fill_downloads_the_range_before_calculating(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """同一只股票先下完全部日期，再写入因子。"""
    from app.services.level2_factors.book import set_book_downloader
    from app.services.level2_factors.build import ensure_symbol
    from app.services.level2_factors.factor_cache import MemoryFactorCache

    monkeypatch.setenv("LEVEL2_PARQUET_CACHE_MAX_DAYS", "0")
    monkeypatch.setenv("LEVEL2_FACTOR_CACHE_MAX_DAYS", "0")
    monkeypatch.setenv("LEVEL2_PARQUET_CACHE_MAX_GB", "10")
    order: list[tuple[str, str]] = []
    payload = {
        "行情": _quote_bytes(),
        "逐笔成交": _parquet_bytes(pd.DataFrame([{
            "时间": "100000000",
            "成交代码": "",
            "成交价格": 100000,
            "成交数量": 100,
            "BS标志": "B",
            "叫买序号": "1",
            "叫卖序号": "2",
        }])),
        "逐笔委托": _parquet_bytes(pd.DataFrame(columns=["时间", "委托类型", "委托代码", "交易所委托号", "委托数量"])),
    }

    def fake(date: str, code: str, ftype: str) -> bytes | None:
        order.append(("download", date))
        return payload[ftype]

    class TracingCache(MemoryFactorCache):
        def upsert(self, symbol: str, date: str, factors: dict) -> None:
            order.append(("calc", date))
            super().upsert(symbol, date, factors)

    store = TracingCache()
    set_book_downloader(fake)
    try:
        ensure_symbol("002074.SZ", ["20260929", "20260930"], parquet_dir=tmp_path, store=store)
    finally:
        set_book_downloader(None)
    split = next(index for index, item in enumerate(order) if item[0] == "calc")
    assert order[:split]
    assert all(kind == "download" for kind, _date in order[:split])
    assert [date for kind, date in order[split:] if kind == "calc"] == ["20260929", "20260930"]
    assert store.has("002074.SZ", "20260929")
    assert store.has("002074.SZ", "20260930")


def test_symbol_fill_downloads_dates_in_parallel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """两个交易日的下载重叠，全部下完后才按日期计算。"""
    import threading
    import time

    from app.services.level2_factors.book import set_book_downloader
    from app.services.level2_factors.build import ensure_symbol
    from app.services.level2_factors.factor_cache import MemoryFactorCache

    monkeypatch.setenv("LEVEL2_PARQUET_CACHE_MAX_DAYS", "0")
    monkeypatch.setenv("LEVEL2_FACTOR_CACHE_MAX_DAYS", "0")
    monkeypatch.setenv("LEVEL2_PARQUET_CACHE_MAX_GB", "10")
    order: list[tuple[str, str]] = []
    state = {"inflight": 0, "peak": 0}
    guard = threading.Lock()
    payload = {
        "行情": _quote_bytes(),
        "逐笔成交": _parquet_bytes(pd.DataFrame([{
            "时间": "100000000",
            "成交代码": "",
            "成交价格": 100000,
            "成交数量": 100,
            "BS标志": "B",
            "叫买序号": "1",
            "叫卖序号": "2",
        }])),
        "逐笔委托": _parquet_bytes(pd.DataFrame(columns=["时间", "委托类型", "委托代码", "交易所委托号", "委托数量"])),
    }

    def fake(date: str, code: str, ftype: str) -> bytes | None:
        with guard:
            state["inflight"] += 1
            state["peak"] = max(state["peak"], state["inflight"])
        try:
            time.sleep(0.05)
            order.append(("download", date))
            return payload[ftype]
        finally:
            with guard:
                state["inflight"] -= 1

    class TracingCache(MemoryFactorCache):
        def upsert(self, symbol: str, date: str, factors: dict) -> None:
            order.append(("calc", date))
            super().upsert(symbol, date, factors)

    store = TracingCache()
    set_book_downloader(fake)
    try:
        ensure_symbol("002074.SZ", ["20260929", "20260930"], parquet_dir=tmp_path, store=store)
    finally:
        set_book_downloader(None)
    assert state["peak"] >= 2
    split = next(index for index, item in enumerate(order) if item[0] == "calc")
    assert all(kind == "download" for kind, _date in order[:split])
    assert [date for kind, date in order[split:] if kind == "calc"] == ["20260929", "20260930"]


def test_books_prefer_project_cache_then_staging_then_baidu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """三类明细先用项目目录，再用 staging，最后才向网盘下载到项目目录。"""
    from app.services.level2_factors.book import download_books, set_book_downloader

    code = "002074.SZ"
    date = "20260929"
    staging = tmp_path / "staging"
    primary = tmp_path / "primary"
    calls: list[str] = []

    def fake(day: str, code_name: str, ftype: str) -> bytes | None:
        calls.append(f"{day}:{ftype}")
        return _quote_bytes() if ftype == "行情" else _parquet_bytes(pd.DataFrame({"时间": ["1"]}))

    monkeypatch.setenv("LEVEL2_STAGING_PARQUET_DIR", str(staging))
    _write_book(staging, date, code)
    set_book_downloader(fake)
    try:
        download_books(primary, date, code)
        assert calls == []
        assert not (primary / date).exists()

        monkeypatch.setenv("LEVEL2_STAGING_PARQUET_DIR", str(tmp_path / "empty-staging"))
        _write_book(primary, date, code)
        download_books(primary, date, code)
        assert calls == []
    finally:
        set_book_downloader(None)

    calls.clear()
    fresh = tmp_path / "fresh"
    set_book_downloader(fake)
    try:
        download_books(fresh, date, code)
        assert calls
        assert (fresh / date / code / "行情.parquet").is_file()
    finally:
        set_book_downloader(None)


def test_factor_day_reads_d1_when_no_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """生产路径不传 directory 时只读 D1；显式 directory 仅供单测。"""
    from app.services.level2_factor_panel import clear_panel_cache, enrich_panel
    from app.services.level2_factors import d1_client, d1_factors

    clear_panel_cache()
    fetched: list[str] = []

    def fetch_symbols(symbols, dates):
        fetched.append(("symbols", list(symbols), list(dates)))
        return [{
            "trade_date": "20260929",
            "symbol": "002074.SZ",
            "l2_active_net_buy": 0.9,
        }]

    def warmup_dates(symbol, before, limit=19):
        del symbol, before, limit
        return []

    index = pd.to_datetime(["2026-09-29"])
    frame = pd.DataFrame({
        "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0],
    }, index=index)
    members = [{"key": "CNStock:002074.SZ", "market": "CNStock", "symbol": "002074"}]
    monkeypatch.setattr(d1_client, "configured", lambda: True)
    monkeypatch.setattr(d1_factors, "fetch_symbols", fetch_symbols)
    monkeypatch.setattr(d1_factors, "warmup_dates", warmup_dates)
    try:
        enriched = enrich_panel({"CNStock:002074.SZ": frame}, members)
        assert fetched
        assert enriched["CNStock:002074.SZ"]["l2_active_net_buy"].iloc[0] == pytest.approx(0.9)

        clear_panel_cache()
        fetched.clear()
        local = pd.DataFrame({
            "trade_date": ["20260929"],
            "symbol": ["002074.SZ"],
            "l2_active_net_buy": [0.1],
        })
        local.to_parquet(tmp_path / "20260929.parquet", index=False)
        enriched = enrich_panel({"CNStock:002074.SZ": frame}, members, directory=tmp_path)
        assert fetched == []
        assert enriched["CNStock:002074.SZ"]["l2_active_net_buy"].iloc[0] == pytest.approx(0.1)
    finally:
        clear_panel_cache()


def test_project_books_are_removed_after_factors_and_staging_stays(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """因子写完后只删项目缓存。staging 里的同名明细还在。"""
    from app.services.level2_factors.build import ensure_symbol
    from app.services.level2_factors.factor_cache import MemoryFactorCache

    monkeypatch.setenv("LEVEL2_PARQUET_CACHE_MAX_DAYS", "0")
    monkeypatch.setenv("LEVEL2_PARQUET_CACHE_MAX_GB", "10")
    monkeypatch.setenv("LEVEL2_FACTOR_CACHE_MAX_DAYS", "0")
    primary = tmp_path / "primary"
    staging = tmp_path / "staging"
    monkeypatch.setenv("LEVEL2_STAGING_PARQUET_DIR", str(staging))
    code = "002074.SZ"
    for date in ("20260929", "20260930"):
        _write_book(primary, date, code)
        _write_book(staging, date, code)
    store = MemoryFactorCache()
    ensure_symbol(code, ["20260929", "20260930"], parquet_dir=primary, store=store)
    assert store.has(code, "20260929")
    assert store.has(code, "20260930")
    assert not (primary / "20260929").exists()
    assert not (primary / "20260930").exists()
    assert (staging / "20260929" / code / "行情.parquet").is_file()
    assert (staging / "20260930" / code / "逐笔成交.parquet").is_file()

    _write_book(primary, "20260929", code)
    ensure_symbol(code, ["20260929"], parquet_dir=primary, store=store)
    assert not (primary / "20260929").exists()
    assert (staging / "20260929" / code / "行情.parquet").is_file()
