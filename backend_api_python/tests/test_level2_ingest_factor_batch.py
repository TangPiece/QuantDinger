"""批量因子：先写本地日频文件再上传，干跑不调用因子步骤。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


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


def test_factor_file_is_written_before_r2_upload(tmp_path, monkeypatch):
    """两只股票并行算完后才上传。对象键在 l2_factors 下，不连真实网盘。"""
    from app.services.level2_ingest import config
    from app.services.level2_ingest.factor_batch import build_and_upload_dates

    monkeypatch.setattr(config, "R2_FACTOR_PREFIX", "l2_factors")
    date = "20260929"
    output = tmp_path / "factors"
    books = tmp_path / "parquet"
    snap = pd.DataFrame([_snapshot_row()])
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
    for code in ("600000.SH", "000001.SZ"):
        folder = books / date / code
        folder.mkdir(parents=True)
        snap.to_parquet(folder / "行情.parquet", index=False)
        trades.to_parquet(folder / "逐笔成交.parquet", index=False)
        orders.to_parquet(folder / "逐笔委托.parquet", index=False)

    seen: list[str] = []

    def uploader(key: str, payload: bytes) -> None:
        written = output / f"{date}.parquet"
        assert written.is_file()
        assert payload == written.read_bytes()
        seen.append(key)

    assert build_and_upload_dates(
        [date],
        workers=2,
        parquet_root=books,
        output_dir=output,
        uploader=uploader,
    )
    assert seen == [f"l2_factors/2026/202609/{date}.parquet"]
    panel = pd.read_parquet(output / f"{date}.parquet")
    assert set(panel["symbol"]) == {"600000.SH", "000001.SZ"}
    from app.services.level2_factors.names import stored_columns

    assert list(panel.columns) == stored_columns()


def _write_symbol_csv(root: Path, date: str, code: str) -> None:
    """写入三类 gb18030 CSV，供 source=csv 因子路径使用。"""
    folder = root / date / code
    folder.mkdir(parents=True, exist_ok=True)
    snap_cols = list(_snapshot_row().keys())
    snap_line = ",".join(str(_snapshot_row()[c]) for c in snap_cols)
    (folder / "行情.csv").write_bytes((",".join(snap_cols) + "\n" + snap_line + "\n").encode("gb18030"))
    trade_header = "成交代码,时间,成交价格,成交数量,BS标志,叫买序号,叫卖序号,\n"
    trade_row = "0,100000000,100000,100,B,1,2,\n"
    (folder / "逐笔成交.csv").write_bytes((trade_header + trade_row).encode("gb18030"))
    order_header = "时间,委托类型,委托代码,交易所委托号,委托数量,\n"
    (folder / "逐笔委托.csv").write_bytes(order_header.encode("gb18030"))


def test_dry_run_does_not_calculate_factors(tmp_path, monkeypatch):
    """整批转换的干跑只调度日期，不调用因子上传。"""
    from app.services.level2_ingest import convert_all

    (tmp_path / "20260929").mkdir()
    monkeypatch.setattr(convert_all.config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(
        convert_all,
        "convert_one_local",
        lambda date, **_kwargs: {
            "date": date,
            "source": "local",
            "stats": {"rows": 0, "symbols": 1, "uploaded": False, "skipped": False},
            "ok": True,
            "reason": "dry_run",
        },
    )
    called = []
    monkeypatch.setattr(
        convert_all.factor_batch,
        "write_trade_date",
        lambda *args, **kwargs: called.append(("write", args, kwargs)) or None,
    )
    monkeypatch.setattr(
        convert_all.factor_batch,
        "_upload_factor_file",
        lambda *args, **kwargs: called.append(("upload", args, kwargs)),
    )
    assert convert_all.main(["--dry-run", "--local-only"]) == 0
    assert called == []


def test_write_trade_date_from_csv(tmp_path):
    """三类 CSV 齐全时 source=csv 可写出日宽表。"""
    from app.services.level2_ingest.factor_batch import write_trade_date
    from app.services.level2_factors.names import stored_columns

    date = "20260929"
    raw = tmp_path / "raw"
    output = tmp_path / "factors"
    for code in ("600000.SH", "000001.SZ"):
        _write_symbol_csv(raw, date, code)

    path = write_trade_date(
        date,
        output,
        source="csv",
        csv_root=raw,
        workers=2,
    )
    assert path is not None and path.is_file()
    panel = pd.read_parquet(path)
    assert set(panel["symbol"]) == {"600000.SH", "000001.SZ"}
    assert list(panel.columns) == stored_columns()


def test_convert_all_uploads_from_csv_without_staging_parquet(tmp_path, monkeypatch):
    """convert_all 单日从 CSV 算因子并上传，不写 staging 明细 Parquet。"""
    from app.services.level2_ingest import convert_all

    date = "20260929"
    raw = tmp_path / "raw"
    staging = tmp_path / "staging"
    factors = staging / "factors"
    parquet = staging / "parquet"
    _write_symbol_csv(raw, date, "600000.SH")
    monkeypatch.setattr(convert_all.config, "DATA_ROOT", raw)
    monkeypatch.setattr(convert_all.config, "STAGING_ROOT", staging)
    monkeypatch.setattr(convert_all.config, "STAGING_PARQUET", parquet)
    monkeypatch.setattr(convert_all, "_MIN_FACTOR_ROWS", 1)
    monkeypatch.setattr(convert_all.factor_batch, "default_output_dir", lambda: factors)

    uploaded: list[str] = []

    def fake_upload(path, uploader):
        del uploader
        uploaded.append(path.name)
        path.unlink(missing_ok=True)

    monkeypatch.setattr(convert_all.factor_batch, "_upload_factor_file", fake_upload)
    monkeypatch.setattr(convert_all, "delete_sources", lambda *_args, **_kwargs: [])

    rec = convert_all.convert_one_local(
        date,
        delete=True,
        dry_run=False,
        skip_existing=True,
        equities_only=True,
        workers=1,
    )
    assert rec["ok"] is True
    assert rec["stats"]["uploaded"] is True
    assert rec["stats"]["rows"] == 1
    assert uploaded == [f"{date}.parquet"]
    assert not parquet.exists() or not any(parquet.rglob("*.parquet"))
    assert (factors / "_uploaded" / f"{date}.json").is_file()


def test_factor_main_dry_run_does_not_calculate(tmp_path, monkeypatch):
    """单独命令的干跑只列出 staging 里的日期。"""
    from app.services.level2_ingest import config
    from app.services.level2_ingest import factor_batch

    (tmp_path / "20260930").mkdir()
    (tmp_path / "20260929").mkdir()
    monkeypatch.setattr(config, "STAGING_PARQUET", tmp_path)
    called = []
    monkeypatch.setattr(
        factor_batch,
        "build_and_upload_dates",
        lambda *args, **kwargs: called.append((args, kwargs)) or True,
    )
    assert factor_batch.main(["--dry-run"]) == 0
    assert called == []


def test_factor_main_passes_dates_oldest_first(tmp_path, monkeypatch):
    """指定日期时按从早到晚交给计算，不读真实归档。"""
    from app.services.level2_ingest import config
    from app.services.level2_ingest import factor_batch

    for date in ("20260930", "20260929", "20260928"):
        (tmp_path / date).mkdir()
    monkeypatch.setattr(config, "STAGING_PARQUET", tmp_path)
    called = []
    monkeypatch.setattr(
        factor_batch,
        "build_and_upload_dates",
        lambda *args, **kwargs: called.append((args, kwargs)) or True,
    )
    assert factor_batch.main(["--dates", "20260930", "20260928", "--workers", "4"]) == 0
    assert called[0][0][0] == ["20260928", "20260930"]
    assert called[0][1]["workers"] == 4
    assert called[0][1]["rebuild_symbols"] is False


def test_force_all_dates_rebuilds_symbol_mirrors(tmp_path, monkeypatch):
    """整批 --force 才在日文件上传后重建股票镜像。指定日期的 --force 不建。"""
    from app.services.level2_ingest import config
    from app.services.level2_ingest import factor_batch

    for date in ("20260929", "20260930"):
        (tmp_path / date).mkdir()
    monkeypatch.setattr(config, "STAGING_PARQUET", tmp_path)
    called = []
    monkeypatch.setattr(
        factor_batch,
        "build_and_upload_dates",
        lambda *args, **kwargs: called.append(kwargs) or True,
    )
    assert factor_batch.main(["--force"]) == 0
    assert called[0]["force"] is True
    assert called[0]["rebuild_symbols"] is True

    called.clear()
    assert factor_batch.main(["--dates", "20260929", "--force"]) == 0
    assert called[0]["force"] is True
    assert called[0]["rebuild_symbols"] is False


def test_symbol_mirrors_wait_until_every_day_uploads(tmp_path, monkeypatch):
    """有一天上传失败时不重建镜像，避免残缺日文件盖掉已有的股票历史。"""
    from app.services.level2_ingest import factor_batch

    calls: list[Path] = []
    monkeypatch.setattr(factor_batch, "list_book_codes", lambda date, parquet_root=None: ["600000.SH"])
    monkeypatch.setattr(
        factor_batch,
        "write_trade_date",
        lambda date, output_dir, **kwargs: Path(output_dir) / f"{date}.parquet",
    )
    monkeypatch.setattr(factor_batch, "_upload_factor_file", lambda path, uploader: None)
    monkeypatch.setattr(factor_batch, "_rebuild_symbol_mirrors", lambda directory: calls.append(directory) or True)

    output = tmp_path / "factors"
    assert factor_batch.build_and_upload_dates(
        ["20260929"],
        output_dir=output,
        force=True,
        rebuild_symbols=True,
    )
    assert calls == [output]

    def fail_upload(path, uploader):
        raise RuntimeError("upload failed")

    calls.clear()
    monkeypatch.setattr(factor_batch, "_upload_factor_file", fail_upload)
    assert not factor_batch.build_and_upload_dates(
        ["20260929"],
        output_dir=output,
        force=True,
        rebuild_symbols=True,
    )
    assert calls == []


def test_factor_download_falls_back_to_flat_key(monkeypatch):
    """新路径没有对象时，仍读改分层之前的扁平键。"""
    from app.services.level2_factors import r2_factors

    seen: list[str] = []
    monkeypatch.setenv("R2_FACTOR_PREFIX", "l2_factors")

    def get_object(date: str, key: str) -> bytes | None:
        del date
        seen.append(key)
        if key.endswith("/20260929.parquet") and key.count("/") == 1:
            return b"old"
        return None

    monkeypatch.setattr(r2_factors, "_configured", lambda: True)
    monkeypatch.setattr(r2_factors, "_downloader", None)
    monkeypatch.setattr(r2_factors, "_get_object", get_object)
    assert r2_factors.factor_object_key("20260929") == "l2_factors/2026/202609/20260929.parquet"
    assert r2_factors.download_factor_file("20260929") == b"old"
    assert seen == [
        "l2_factors/2026/202609/20260929.parquet",
        "l2_factors/20260929.parquet",
    ]
