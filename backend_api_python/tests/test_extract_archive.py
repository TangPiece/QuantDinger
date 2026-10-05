"""extract.extract_archive 整包解压行为测试。"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.level2_ingest import config, extract


def _make_archive(archive_path: Path, member_files: dict[str, str]) -> Path:
    """用 bsdtar 打出可被 `tar -xf` 读取的归档（扩展名 .7z 即可）。

    member_files: 归档内相对路径 → 文件内容。
    按 staging 下顶层条目打包，避免成员带 `./` 前缀干扰布局探测。
    """
    staging = archive_path.parent / f"_staging_{archive_path.stem}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    for rel, content in member_files.items():
        path = staging / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    top_entries = sorted(p.name for p in staging.iterdir())
    subprocess.check_call(
        ["tar", "-cf", str(archive_path), "-C", str(staging), *top_entries],
    )
    shutil.rmtree(staging)
    return archive_path

def test_extract_archive_skips_nonempty_day_dir(tmp_path: Path, monkeypatch, capsys):
    """目标日目录已存在且非空时跳过解压，不触碰假 .7z 内容。"""
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    date = "20260101"
    day_dir = tmp_path / date
    day_dir.mkdir()
    (day_dir / "000001.SZ").mkdir()
    seven_z = tmp_path / f"{date}.7z"
    seven_z.write_bytes(b"not-a-real-archive")

    result = extract.extract_archive(seven_z)

    assert result == day_dir
    assert "跳过解压" in capsys.readouterr().out


def test_extract_archive_missing_file_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    with pytest.raises(FileNotFoundError):
        extract.extract_archive(tmp_path / "missing.7z")


def test_extract_archive_with_date_prefix(tmp_path: Path, monkeypatch, capsys):
    """归档含 `{date}/{code}/...` 时解到 DATA_ROOT，不产生双层日期。"""
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    date = "20260915"
    seven_z = tmp_path / f"{date}.7z"
    _make_archive(
        seven_z,
        {
            f"{date}/000001.SZ/行情.csv": "a,b\n1,2\n",
            f"{date}/000002.SZ/逐笔成交.csv": "x,y\n3,4\n",
        },
    )

    result = extract.extract_archive(seven_z)

    day_dir = tmp_path / date
    assert result == day_dir
    assert (day_dir / "000001.SZ" / "行情.csv").is_file()
    assert (day_dir / "000002.SZ" / "逐笔成交.csv").is_file()
    # 不应再套一层日期
    assert not (day_dir / date).exists()
    assert "归档含日期前缀" in capsys.readouterr().out


def test_extract_archive_without_date_prefix(tmp_path: Path, monkeypatch):
    """归档为 `{code}/...` 时解到日目录，得到 `{date}/{code}/...`。"""
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    date = "20260916"
    seven_z = tmp_path / f"{date}.7z"
    _make_archive(
        seven_z,
        {
            "000001.SZ/行情.csv": "a,b\n1,2\n",
            "000002.SZ/逐笔委托.csv": "x,y\n3,4\n",
        },
    )

    result = extract.extract_archive(seven_z)

    day_dir = tmp_path / date
    assert result == day_dir
    assert (day_dir / "000001.SZ" / "行情.csv").is_file()
    assert (day_dir / "000002.SZ" / "逐笔委托.csv").is_file()
    assert not (day_dir / date).exists()


def test_extract_archive_flattens_nested_dirty_dir(tmp_path: Path, monkeypatch, capsys):
    """已存在双层日期脏目录时展平并跳过解压。"""
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    date = "20260915"
    day_dir = tmp_path / date
    nested = day_dir / date
    code_dir = nested / "000001.SZ"
    code_dir.mkdir(parents=True)
    (code_dir / "行情.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    seven_z = tmp_path / f"{date}.7z"
    seven_z.write_bytes(b"not-a-real-archive")

    result = extract.extract_archive(seven_z)

    assert result == day_dir
    assert (day_dir / "000001.SZ" / "行情.csv").is_file()
    assert not nested.exists()
    out = capsys.readouterr().out
    assert "展平双层日期目录" in out
    assert "已修复双层目录" in out


def test_convert_local_date_sees_codes_after_date_prefix_extract(
    tmp_path: Path, monkeypatch
):
    """解压带日期前缀归档后，convert_local_date 能扫到股票代码目录。"""
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "STAGING_PARQUET", tmp_path / "parquet")
    date = "20260915"
    seven_z = tmp_path / f"{date}.7z"
    _make_archive(
        seven_z,
        {f"{date}/000001.SZ/行情.csv": "时间,价格\n09:30:00,10.0\n"},
    )

    extract.extract_archive(seven_z)

    day_dir = tmp_path / date
    codes = sorted(p.name for p in day_dir.iterdir() if p.is_dir())
    assert codes == ["000001.SZ"]
    assert config.local_csv_path(date, "000001.SZ", "行情").is_file()
