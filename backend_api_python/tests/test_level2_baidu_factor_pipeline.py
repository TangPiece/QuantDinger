"""百度按日因子流水线：先并行下完全日，再计算上传，成功后清明细。"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
import requests

from app.services.level2_factors.book import set_book_downloader, set_remote_lister
from app.services.level2_ingest import baidu_factor_pipeline as pipeline


@pytest.fixture(autouse=True)
def _hide_host_staging(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """测试不要读到本机 staging，避免把真实明细当成下载结果。"""
    monkeypatch.setenv("LEVEL2_STAGING_PARQUET_DIR", str(tmp_path_factory.mktemp("no-staging")))


@pytest.fixture(autouse=True)
def _reset_book_hooks():
    """每个用例结束后清掉注入的下载器和远程列表。"""
    yield
    set_book_downloader(None)
    set_remote_lister(None)


def _parquet_bytes(frame: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.to_parquet(buffer, index=False)
    return buffer.getvalue()


def _book_payload() -> dict[str, bytes]:
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
    return {
        "行情": _parquet_bytes(snap),
        "逐笔成交": _parquet_bytes(trades),
        "逐笔委托": _parquet_bytes(orders),
    }


def test_iter_calendar_dates_inclusive():
    assert pipeline.iter_calendar_dates("20251009", "20251011") == [
        "20251009",
        "20251010",
        "20251011",
    ]


def test_download_all_then_calc_then_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """两只股票先全部下载到本地，再计算；上传成功后当日本地明细被清掉。"""
    from app.services.level2_ingest import config

    monkeypatch.setattr(config, "R2_FACTOR_PREFIX", "l2_factors")
    books = tmp_path / "books"
    output = tmp_path / "factors"
    date = "20260601"
    codes = ["600000.SH", "000001.SZ"]
    payload = _book_payload()
    download_order: list[str] = []
    calc_seen_before_upload: list[str] = []

    def fake_download(day: str, code: str, ftype: str) -> bytes | None:
        download_order.append(code)
        return payload[ftype]

    set_remote_lister(lambda day: codes if day == date else [])
    set_book_downloader(fake_download)

    original_write = pipeline.factor_batch.write_trade_date

    def wrapped_write(day, output_dir, **kwargs):
        # 计算开始前，两只股票的三类明细都应已落地。
        for code in codes:
            for ftype in ("行情", "逐笔成交", "逐笔委托"):
                assert (books / day / code / f"{ftype}.parquet").is_file()
            calc_seen_before_upload.append(code)
        return original_write(day, output_dir, **kwargs)

    monkeypatch.setattr(pipeline.factor_batch, "write_trade_date", wrapped_write)

    uploaded: list[str] = []

    def uploader(key: str, body: bytes) -> None:
        uploaded.append(key)
        assert (output / f"{date}.parquet").is_file()
        assert body == (output / f"{date}.parquet").read_bytes()

    status = pipeline.process_date(
        date,
        books_dir=books,
        output_dir=output,
        download_workers=2,
        workers=1,
        uploader=uploader,
    )
    assert status == "ok"
    assert set(download_order) == set(codes)
    assert set(calc_seen_before_upload) == set(codes)
    assert uploaded == [f"l2_factors/2026/202606/{date}.parquet"]
    assert not (books / date).exists()
    assert (output / "_uploaded" / f"{date}.json").is_file()


def test_run_range_skips_uploaded_and_empty_days(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """已上传日期跳过；网盘无代码的日期跳过且不上传。"""
    from app.services.level2_ingest import config

    monkeypatch.setattr(config, "R2_FACTOR_PREFIX", "l2_factors")
    books = tmp_path / "books"
    output = tmp_path / "factors"
    day_ok = "20260602"
    day_empty = "20260603"
    payload = _book_payload()

    # 预先标记已上传的日子。
    done = output / "_done"
    uploaded_mark = output / "_uploaded"
    done.mkdir(parents=True)
    uploaded_mark.mkdir(parents=True)
    (output / "20260601.parquet").write_bytes(b"old")
    (done / "20260601.json").write_text('{"date":"20260601","rows":1}', encoding="utf-8")
    (uploaded_mark / "20260601.json").write_text('{"date":"20260601"}', encoding="utf-8")

    set_remote_lister(lambda day: ["600000.SH"] if day == day_ok else [])
    set_book_downloader(lambda day, code, ftype: payload[ftype])

    uploaded: list[str] = []

    def uploader(key: str, body: bytes) -> None:
        uploaded.append(key)

    assert pipeline.run_range(
        "20260601",
        "20260603",
        books_dir=books,
        output_dir=output,
        download_workers=1,
        workers=1,
        uploader=uploader,
    )
    assert uploaded == [f"l2_factors/2026/202606/{day_ok}.parquet"]
    assert not (books / day_empty).exists()
    assert (output / "_uploaded" / f"{day_ok}.json").is_file()


def test_second_day_waits_until_first_uploads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """第一日上传成功后才进入第二日下载。"""
    from app.services.level2_ingest import config

    monkeypatch.setattr(config, "R2_FACTOR_PREFIX", "l2_factors")
    books = tmp_path / "books"
    output = tmp_path / "factors"
    payload = _book_payload()
    events: list[str] = []

    set_remote_lister(lambda day: ["600000.SH"])
    set_book_downloader(lambda day, code, ftype: payload[ftype] if events.append(f"dl:{day}") is None else payload[ftype])

    def uploader(key: str, body: bytes) -> None:
        events.append(f"up:{Path(key).stem}")

    assert pipeline.run_range(
        "20260601",
        "20260602",
        books_dir=books,
        output_dir=output,
        download_workers=1,
        workers=1,
        uploader=uploader,
    )
    # 两类事件各出现两次；同一天的下载必须早于上传，且第一日上传早于第二日下载。
    assert events.index("up:20260601") > events.index("dl:20260601")
    assert events.index("dl:20260602") > events.index("up:20260601")
    assert events.index("up:20260602") > events.index("dl:20260602")


def test_force_reprocesses_uploaded_day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--force 忽略已上传标记并重新上传。"""
    from app.services.level2_ingest import config

    monkeypatch.setattr(config, "R2_FACTOR_PREFIX", "l2_factors")
    books = tmp_path / "books"
    output = tmp_path / "factors"
    date = "20260601"
    payload = _book_payload()

    (output / "_done").mkdir(parents=True)
    (output / "_uploaded").mkdir(parents=True)
    (output / f"{date}.parquet").write_bytes(b"old")
    (output / "_done" / f"{date}.json").write_text('{"date":"20260601","rows":1}', encoding="utf-8")
    (output / "_uploaded" / f"{date}.json").write_text('{"date":"20260601"}', encoding="utf-8")

    set_remote_lister(lambda day: ["600000.SH"] if day == date else [])
    set_book_downloader(lambda day, code, ftype: payload[ftype])
    uploaded: list[str] = []

    assert pipeline.run_range(
        date,
        date,
        books_dir=books,
        output_dir=output,
        download_workers=1,
        workers=1,
        force=True,
        uploader=lambda key, body: uploaded.append(key),
    )
    assert uploaded == [f"l2_factors/2026/202606/{date}.parquet"]


def test_upload_failure_stops_next_day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """上传失败时保留本地明细，且不处理后续日期。"""
    books = tmp_path / "books"
    output = tmp_path / "factors"
    payload = _book_payload()
    downloaded_days: list[str] = []

    set_remote_lister(lambda day: ["600000.SH"])
    set_book_downloader(
        lambda day, code, ftype: (
            downloaded_days.append(day) or payload[ftype]
        )
    )

    def uploader(key: str, body: bytes) -> None:
        raise RuntimeError("r2 down")

    assert not pipeline.run_range(
        "20260601",
        "20260602",
        books_dir=books,
        output_dir=output,
        download_workers=1,
        workers=1,
        uploader=uploader,
    )
    assert "20260601" in downloaded_days
    assert "20260602" not in downloaded_days
    assert (books / "20260601" / "600000.SH" / "行情.parquet").is_file()
    assert not (output / "_uploaded" / "20260601.json").is_file()


def test_dry_run_prints_dates_without_download(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """干跑只打印日期，不触发下载。"""
    called = []
    set_remote_lister(lambda day: called.append(day) or ["600000.SH"])
    assert pipeline.run_range(
        "20260601",
        "20260602",
        books_dir=tmp_path / "books",
        output_dir=tmp_path / "factors",
        dry_run=True,
    )
    assert called == []
    out = capsys.readouterr().out
    assert "20260601" in out and "20260602" in out


def test_low_download_success_skips_upload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """下载成功率低于 90% 时不算因子、不上传，已成功的本地明细保留。"""
    books = tmp_path / "books"
    output = tmp_path / "factors"
    date = "20260601"
    codes = [f"60000{i}.SH" for i in range(10)]
    payload = _book_payload()
    uploaded: list[str] = []

    def fake_download(day: str, code: str, ftype: str) -> bytes | None:
        # 只有第一只成功，成功率 10%。
        if code == codes[0]:
            return payload[ftype]
        raise requests.exceptions.ConnectTimeout("slow")

    set_remote_lister(lambda day: codes if day == date else [])
    set_book_downloader(fake_download)

    # download_books 需要把异常传出；注入的 downloader 抛错时 book._fetch 会抛。
    status = pipeline.process_date(
        date,
        books_dir=books,
        output_dir=output,
        download_workers=1,
        workers=1,
        uploader=lambda key, body: uploaded.append(key),
    )
    assert status == "failed"
    assert uploaded == []
    assert (books / date / codes[0] / "行情.parquet").is_file()
    assert not (output / f"{date}.parquet").exists()


def test_download_submits_in_batches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """按批提交，不会一次把全部股票挂进同一个线程池。"""
    from concurrent.futures import ThreadPoolExecutor

    books = tmp_path / "books"
    output = tmp_path / "factors"
    date = "20260601"
    codes = [f"60000{i}.SH" for i in range(5)]
    payload = _book_payload()
    created: list = []
    real = ThreadPoolExecutor

    class SpyPool(real):
        def __init__(self, max_workers=None, *args, **kwargs):
            super().__init__(max_workers=max_workers, *args, **kwargs)
            self.submitted = 0
            created.append(self)

        def submit(self, fn, *args, **kwargs):
            self.submitted += 1
            return super().submit(fn, *args, **kwargs)

    monkeypatch.setattr(pipeline, "ThreadPoolExecutor", SpyPool)
    set_remote_lister(lambda day: codes if day == date else [])
    set_book_downloader(lambda day, code, ftype: payload[ftype])
    status = pipeline.process_date(
        date,
        books_dir=books,
        output_dir=output,
        download_workers=2,
        workers=1,
        uploader=lambda key, body: None,
    )
    assert status == "ok"
    assert [pool.submitted for pool in created] == [2, 2, 1]


def test_ready_symbol_skips_download(tmp_path: Path):
    """本地三类明细已齐的股票不再下载。"""
    books = tmp_path / "books"
    output = tmp_path / "factors"
    date = "20260601"
    ready = "600000.SH"
    missing = "000001.SZ"
    payload = _book_payload()
    folder = books / date / ready
    folder.mkdir(parents=True)
    for name, blob in payload.items():
        (folder / f"{name}.parquet").write_bytes(blob)
    called: list[str] = []

    def fake(day: str, code: str, ftype: str) -> bytes:
        called.append(code)
        return payload[ftype]

    set_remote_lister(lambda day: [ready, missing] if day == date else [])
    set_book_downloader(fake)
    status = pipeline.process_date(
        date,
        books_dir=books,
        output_dir=output,
        download_workers=1,
        workers=1,
        uploader=lambda key, body: None,
    )
    assert status == "ok"
    assert ready not in called
    assert missing in called
