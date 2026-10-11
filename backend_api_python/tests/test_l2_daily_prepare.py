"""l2_daily：CSV 直算、解压准备、删源。"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def _write_symbol_csv(raw: Path, date: str, code: str) -> None:
    folder = raw / date / code
    folder.mkdir(parents=True, exist_ok=True)
    quote = (
        "时间,申买价1,申卖价1,申买量1,申卖量1,\n"
        "100000000,100000,100100,100,80,\n"
    )
    (folder / "行情.csv").write_bytes(quote.encode("gb18030"))
    trade = (
        "时间,成交代码,成交价格,成交数量,BS标志,叫买序号,叫卖序号,\n"
        "100000000,0,100000,100,B,1,10,\n"
    )
    (folder / "逐笔成交.csv").write_bytes(trade.encode("gb18030"))
    order = (
        "时间,委托类型,委托代码,交易所委托号,委托数量,委托价格,\n"
        "093100000,A,B,1,1000,100000,\n"
    )
    (folder / "逐笔委托.csv").write_bytes(order.encode("gb18030"))


def test_ensure_day_csv_skips_when_present(tmp_path):
    from app.services.level2_factors.l2_daily import prepare

    date = "20261009"
    _write_symbol_csv(tmp_path, date, "600000.SH")
    path = prepare.ensure_day_csv(date, tmp_path)
    assert path == tmp_path / date
    assert (path / "600000.SH" / "逐笔成交.csv").is_file()


def test_run_batch_from_csv_deletes_sources(tmp_path, monkeypatch):
    from app.services.level2_factors.l2_daily import orchestrator, storage

    date = "20261009"
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    _write_symbol_csv(raw, date, "600000.SH")
    storage.set_r2_uploader(lambda key, payload: None)

    summary = orchestrator.run_batch(
        raw_root=raw,
        output_root=out,
        groups=["trade"],
        dates=[date],
        force=True,
        upload_r2=False,
        seed_defs=False,
        compact_months=False,
        delete_sources=True,
        dry_run=False,
        local_only=True,
    )
    assert summary["processed"] >= 1
    assert summary["failed"] == 0
    assert not (raw / date).exists()
    panel = storage.read_day(out, date)
    assert panel is not None
    assert np.isfinite(panel.loc[0, "l2_trade_count"])


def test_run_batch_no_delete_keeps_csv(tmp_path):
    from app.services.level2_factors.l2_daily import orchestrator, storage

    date = "20261010"
    raw = tmp_path / "raw"
    out = tmp_path / "out"
    _write_symbol_csv(raw, date, "000001.SZ")
    storage.set_r2_uploader(lambda key, payload: None)

    summary = orchestrator.run_batch(
        raw_root=raw,
        output_root=out,
        groups=["trade"],
        dates=[date],
        force=True,
        upload_r2=False,
        seed_defs=False,
        compact_months=False,
        delete_sources=False,
        dry_run=False,
        local_only=True,
    )
    assert summary["processed"] >= 1
    assert (raw / date / "000001.SZ" / "逐笔成交.csv").is_file()


def test_engine_reads_csv_directly(tmp_path):
    from app.services.level2_factors.l2_daily.engine import calc_group_for_symbol

    date = "20261011"
    _write_symbol_csv(tmp_path, date, "600000.SH")
    row = calc_group_for_symbol(tmp_path, date, "600000.SH", "trade")
    assert row is not None
    assert row["l2_trade_count"] == 1


def test_dry_run_batch_does_not_delete(tmp_path):
    from app.services.level2_factors.l2_daily import orchestrator

    date = "20261012"
    raw = tmp_path / "raw"
    _write_symbol_csv(raw, date, "600000.SH")
    summary = orchestrator.run_batch(
        raw_root=raw,
        output_root=tmp_path / "out",
        groups=["trade"],
        dates=[date],
        dry_run=True,
        delete_sources=True,
        local_only=True,
        seed_defs=False,
        upload_r2=False,
    )
    assert summary["skipped"] >= 1
    assert (raw / date / "600000.SH" / "逐笔成交.csv").is_file()


def test_ensure_day_csv_extracts_7z(tmp_path, monkeypatch):
    from app.services.level2_factors.l2_daily import prepare

    date = "20261013"
    raw = tmp_path / "raw"
    raw.mkdir()
    archive = raw / f"{date}.7z"
    archive.write_bytes(b"fake")

    def fake_extract(seven_z, *, dest_root=None):
        dest = Path(dest_root or raw)
        _write_symbol_csv(dest, date, "600000.SH")
        return dest / date

    monkeypatch.setattr(
        "app.services.level2_ingest.extract.extract_archive",
        fake_extract,
    )
    path = prepare.ensure_day_csv(date, raw)
    assert path == raw / date
    assert (raw / date / "600000.SH" / "逐笔成交.csv").is_file()


def test_run_batch_from_7z_then_calc(tmp_path, monkeypatch):
    from app.services.level2_factors.l2_daily import orchestrator, prepare, storage

    date = "20261014"
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / f"{date}.7z").write_bytes(b"fake")

    def fake_extract(seven_z, *, dest_root=None):
        dest = Path(dest_root or raw)
        _write_symbol_csv(dest, date, "600000.SH")
        return dest / date

    monkeypatch.setattr(
        "app.services.level2_ingest.extract.extract_archive",
        fake_extract,
    )
    storage.set_r2_uploader(lambda key, payload: None)
    summary = orchestrator.run_batch(
        raw_root=raw,
        output_root=tmp_path / "out",
        groups=["trade"],
        dates=[date],
        force=True,
        upload_r2=False,
        seed_defs=False,
        compact_months=False,
        delete_sources=True,
        z7_only=True,
    )
    assert summary["processed"] >= 1
    assert summary["failed"] == 0
    assert not (raw / date).exists()
    assert not (raw / f"{date}.7z").exists()
