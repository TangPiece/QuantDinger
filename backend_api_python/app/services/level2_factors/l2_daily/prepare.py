"""解压准备与日期发现。不转明细 Parquet，只保证当日 CSV 目录可用。"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.services.level2_ingest import config, extract


def discover_local_dates(raw_root: Path, only: list[str] | None = None) -> list[str]:
    """扫描已解压目录 raw_root/{date}/。"""
    root = Path(raw_root)
    if not root.is_dir():
        return []
    dates = sorted(
        p.name for p in root.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 8
    )
    if only:
        wanted = set(only)
        dates = [d for d in dates if d in wanted]
    return dates


def discover_7z_dates(raw_root: Path, only: list[str] | None = None) -> list[str]:
    """扫描 raw_root/*.7z。``only`` 只做过滤，缺失留给 ensure_day_csv 报错。"""
    root = Path(raw_root)
    if not root.is_dir():
        dates: list[str] = []
    else:
        dates = sorted(p.stem for p in root.glob("*.7z"))
    if only:
        wanted = set(only)
        dates = [d for d in dates if d in wanted]
    return dates


def day_has_csv(raw_root: Path, trade_date: str) -> bool:
    day = Path(raw_root) / str(trade_date)
    if not day.is_dir():
        return False
    return any(day.rglob("*.csv"))


def ensure_day_csv(trade_date: str, raw_root: Path, *, dry_run: bool = False) -> Path:
    """保证 {raw_root}/{date}/ 下有 CSV。已有则跳过；否则解压 {date}.7z。"""
    root = Path(raw_root)
    day_dir = root / str(trade_date)
    if day_has_csv(root, trade_date):
        return day_dir
    seven_z = root / f"{trade_date}.7z"
    if not seven_z.is_file():
        raise FileNotFoundError(f"无已解压 CSV 且找不到归档: {seven_z}")
    if dry_run:
        print(f"[{trade_date}] dry-run：将解压 {seven_z.name}", flush=True)
        return day_dir
    return extract.extract_archive(seven_z, dest_root=root)


def delete_day_sources(trade_date: str, raw_root: Path, *, dry_run: bool = False) -> list[str]:
    """删除 raw_root/{date}/ 与 {date}.7z。"""
    deleted: list[str] = []
    root = Path(raw_root)
    day_dir = root / str(trade_date)
    seven_z = root / f"{trade_date}.7z"
    if day_dir.is_dir():
        if not dry_run:
            shutil.rmtree(day_dir)
        deleted.append(str(day_dir))
    if seven_z.is_file():
        if not dry_run:
            seven_z.unlink()
        deleted.append(str(seven_z))
    return deleted


def default_raw_root() -> Path:
    return Path(config.DATA_ROOT)
