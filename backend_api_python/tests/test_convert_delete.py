"""convert_local 转换完成后删除源文件。"""
from __future__ import annotations

from pathlib import Path

from app.services.level2_ingest import config
from app.services.level2_ingest.convert_local import (
    _can_delete_sources,
    delete_sources,
    maybe_delete_sources,
)


def _good_stats() -> dict[str, int]:
    return {"total": 15000, "converted": 14900, "skipped": 100, "failed": 0}


def test_can_delete_sources_ok():
    ok, reason = _can_delete_sources(_good_stats())
    assert ok is True
    assert reason == "ok"


def test_can_delete_sources_failed():
    stats = _good_stats()
    stats["failed"] = 1
    ok, _ = _can_delete_sources(stats)
    assert ok is False


def test_can_delete_sources_total_too_small():
    stats = {"total": 100, "converted": 100, "skipped": 0, "failed": 0}
    ok, reason = _can_delete_sources(stats)
    assert ok is False
    assert "10000" in reason


def test_delete_sources_removes_csv_and_7z(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    date = "20260899"
    day_dir = tmp_path / date
    day_dir.mkdir()
    (day_dir / "000001.SZ").mkdir()
    seven_z = tmp_path / f"{date}.7z"
    seven_z.write_bytes(b"fake")

    removed = delete_sources(date, dry_run=False)

    assert not day_dir.exists()
    assert not seven_z.exists()
    assert str(day_dir) in removed
    assert str(seven_z) in removed


def test_delete_sources_dry_run_keeps_files(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    date = "20260898"
    day_dir = tmp_path / date
    day_dir.mkdir()
    seven_z = tmp_path / f"{date}.7z"
    seven_z.write_bytes(b"fake")

    delete_sources(date, dry_run=True)

    assert day_dir.is_dir()
    assert seven_z.is_file()


def test_maybe_delete_sources_skips_when_disabled(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    date = "20260897"
    day_dir = tmp_path / date
    day_dir.mkdir()
    seven_z = tmp_path / f"{date}.7z"
    seven_z.write_bytes(b"fake")

    maybe_delete_sources(date, _good_stats(), enabled=False, dry_run=False)

    assert day_dir.is_dir()
    assert seven_z.is_file()
    assert capsys.readouterr().out == ""


def test_maybe_delete_sources_skips_on_bad_stats(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    date = "20260896"
    day_dir = tmp_path / date
    day_dir.mkdir()
    seven_z = tmp_path / f"{date}.7z"
    seven_z.write_bytes(b"fake")
    stats = _good_stats()
    stats["failed"] = 2

    maybe_delete_sources(date, stats, enabled=True, dry_run=False)

    assert day_dir.is_dir()
    assert seven_z.is_file()
    out = capsys.readouterr().out
    assert "未删除原始文件" in out


def test_maybe_delete_sources_deletes_when_ok(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    date = "20260895"
    day_dir = tmp_path / date
    day_dir.mkdir()
    seven_z = tmp_path / f"{date}.7z"
    seven_z.write_bytes(b"fake")

    maybe_delete_sources(date, _good_stats(), enabled=True, dry_run=False)

    assert not day_dir.exists()
    assert not seven_z.exists()
    out = capsys.readouterr().out
    assert "已删除原始文件" in out
