"""读取行情、逐笔成交、逐笔委托。

目录由 ``LEVEL2_PARQUET_DIR`` 或调用参数指定。未设置时落在
QuantDinger 的 ``data/level2_parquet``，不写到 level2 仓库的 staging。
布局是 ``{目录}/{YYYYMMDD}/{代码}/{行情|逐笔成交|逐笔委托}.parquet``。
本地没有时从百度网盘补到同一路径。这是临时目录：因子写入成功后
会删掉对应股票当天的明细。未算完的日子仍受
``LEVEL2_PARQUET_CACHE_MAX_GB``（默认 10）和
``LEVEL2_PARQUET_CACHE_MAX_DAYS``（默认 370）约束，正在下载的那一天保留。不读 CSV。
"""
from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from .prep import is_equity

FILE_TYPES = ("行情", "逐笔成交", "逐笔委托")
_GB = 1024 ** 3
_downloader: Callable[[str, str, str], bytes | None] | None = None
_remote_lister: Callable[[str], list[str]] | None = None


def set_book_downloader(downloader: Callable[[str, str, str], bytes | None] | None) -> None:
    """测试注入下载器。返回 None 表示网盘没有这个文件。"""
    global _downloader
    _downloader = downloader


def set_remote_lister(lister: Callable[[str], list[str]] | None) -> None:
    """测试注入某一天的远程代码列表。"""
    global _remote_lister
    _remote_lister = lister


def default_parquet_directory() -> Path:
    """项目内明细缓存。本机是 ``backend_api_python/data/level2_parquet``，容器是 ``/app/data/level2_parquet``。"""
    # book.py 在 app/services/level2_factors，往上四级是后端根目录。
    root = Path(__file__).resolve().parents[3] / "data" / "level2_parquet"
    root.mkdir(parents=True, exist_ok=True)
    return root


def parquet_directory() -> Path | None:
    """未设置环境变量时用项目内默认目录。显式路径不存在时返回 None。"""
    raw = os.getenv("LEVEL2_PARQUET_DIR", "").strip()
    if not raw:
        return default_parquet_directory()
    path = Path(raw)
    return path if path.is_dir() else None


def book_path(root: Path, date: str, code: str, ftype: str) -> Path:
    """某日某股某一类明细的 Parquet 路径。"""
    return Path(root) / str(date) / str(code) / f"{ftype}.parquet"


def load_frame(root: Path, date: str, code: str, ftype: str) -> pd.DataFrame:
    """读取一个 Parquet。本地没有则尝试从网盘落下再读。仍没有时抛 ``FileNotFoundError``。"""
    path = book_path(root, date, code, ftype)
    if path.suffix.lower() != ".parquet":
        raise FileNotFoundError(path)
    if not path.is_file():
        payload = _fetch(date, code, ftype)
        if not payload:
            raise FileNotFoundError(path)
        _write_bytes(path, payload)
        # 刚写入的日期不删，避免这一天算到一半文件被上限清掉。
        enforce_book_cache(root, keep_date=str(date))
    return pd.read_parquet(path)


def download_books(root: Path, date: str, code: str) -> None:
    """把缺的三类明细落到项目内缓存。已有文件跳过。

    项目目录或 staging 里三类都在时不再下载，也不把 staging 的文件复制进来。
    只写文件，不读成表，也不按容量删目录。三类都没有时抛 ``FileNotFoundError``。
    """
    if ready_book_root(root, date, code) is not None:
        return
    found = False
    for ftype in FILE_TYPES:
        path = book_path(root, date, code, ftype)
        if path.is_file():
            found = True
            continue
        payload = _fetch(date, code, ftype)
        if not payload:
            continue
        _write_bytes(path, payload)
        found = True
    if not found:
        raise FileNotFoundError(f"{date}/{code} 没有 Parquet 明细")


def _write_bytes(path: Path, payload: bytes) -> None:
    """先写临时文件再替换，避免读到写了一半的 Parquet。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.part")
    temporary.write_bytes(payload)
    temporary.replace(path)


def staging_parquet_directory() -> Path | None:
    """只读的旧明细目录。不存在时返回 None，新下载不会写到这里。

    环境变量指定时只用那一处。没指定时先看 data/level2_staging/parquet，再看容器里的只读挂载。
    """
    raw = os.getenv("LEVEL2_STAGING_PARQUET_DIR", "").strip()
    if raw:
        path = Path(raw)
        return path if path.is_dir() else None
    # 批量转换的明细在 backend data 里；容器里是 compose 的只读挂载。
    host_staging = Path(__file__).resolve().parents[3] / "data" / "level2_staging" / "parquet"
    for candidate in (
        host_staging,
        Path("/level2/staging/parquet"),
    ):
        if candidate.is_dir():
            return candidate
    return None


def discard_symbol_books(root: Path, date: str, code: str) -> None:
    """删掉项目缓存里某股某日的明细。空的日期目录一起去掉。

    只删除 ``root`` 下面的目录。staging 即使算出了因子也不动。
    """
    symbol_dir = Path(root) / str(date) / str(code)
    if not symbol_dir.exists():
        return
    try:
        resolved = symbol_dir.resolve()
        root_resolved = Path(root).resolve()
    except OSError:
        return
    if root_resolved not in resolved.parents:
        return
    staging = staging_parquet_directory()
    if staging is not None:
        try:
            staging_resolved = staging.resolve()
        except OSError:
            staging_resolved = None
        if staging_resolved is not None and (resolved == staging_resolved or staging_resolved in resolved.parents):
            return
    shutil.rmtree(resolved)
    day = resolved.parent
    if day.is_dir() and not any(day.iterdir()):
        day.rmdir()


def books_ready(root: Path, date: str, code: str) -> bool:
    """三类明细文件是否都在这个目录里。"""
    return all(book_path(root, date, code, ftype).is_file() for ftype in FILE_TYPES)


def ready_book_root(primary: Path, date: str, code: str) -> Path | None:
    """先用项目内明细，再用 staging。两边都缺时返回 None，由调用方去网盘下载。"""
    if books_ready(primary, date, code):
        return Path(primary)
    staging = staging_parquet_directory()
    if staging is None:
        return None
    try:
        same = staging.resolve() == Path(primary).resolve()
    except OSError:
        same = False
    if same or not books_ready(staging, date, code):
        return None
    return staging


def load_book(root: Path, date: str, code: str) -> dict[str, pd.DataFrame]:
    """读取行情、逐笔成交、逐笔委托。缺的类型是空表，三类都缺则抛 ``FileNotFoundError``。

    项目目录没有完整三类时，先读 staging，仍没有再下载到项目目录。
    """
    ready = ready_book_root(root, date, code)
    source = ready if ready is not None else Path(root)
    if ready is None:
        try:
            download_books(root, date, code)
        except FileNotFoundError:
            raise
        ready = ready_book_root(root, date, code)
        source = ready if ready is not None else Path(root)
    frames: dict[str, pd.DataFrame] = {}
    missing = 0
    for ftype in FILE_TYPES:
        path = book_path(source, date, code, ftype)
        if not path.is_file():
            frames[ftype] = pd.DataFrame()
            missing += 1
            continue
        frames[ftype] = pd.read_parquet(path)
    if missing == len(FILE_TYPES):
        raise FileNotFoundError(f"{date}/{code} 没有 Parquet 明细")
    return frames


def list_equity_codes(root: Path, date: str) -> list[str]:
    """列出当天目录里的 A 股代码。只认子目录，不扫 CSV。"""
    day = Path(root) / str(date)
    if not day.is_dir():
        return []
    return sorted(child.name for child in day.iterdir() if child.is_dir() and is_equity(child.name))


def list_remote_equity_codes(date: str) -> list[str]:
    """本地这一天还没有目录时，向网盘要代码列表。"""
    if _remote_lister is not None:
        return sorted(code for code in _remote_lister(date) if is_equity(code))
    from .baidu_books import list_equity_codes as remote_codes

    return remote_codes(date)


def cache_limit_bytes() -> int | None:
    """明细缓存上限。未设置时 10GB；小于等于 0 表示不按容量淘汰。"""
    raw = os.getenv("LEVEL2_PARQUET_CACHE_MAX_GB", "").strip()
    if not raw:
        gb = 10.0
    else:
        try:
            gb = float(raw)
        except ValueError:
            gb = 10.0
    if gb <= 0:
        return None
    return int(gb * _GB)


def cache_max_days() -> int | None:
    """明细保留天数。未设置时 370，覆盖近一年；小于等于 0 表示不过期。"""
    raw = os.getenv("LEVEL2_PARQUET_CACHE_MAX_DAYS", "").strip()
    if not raw:
        days = 370
    else:
        try:
            days = int(float(raw))
        except ValueError:
            days = 370
    return days if days > 0 else None


def enforce_book_cache(root: Path, keep_date: str) -> None:
    """先删过期交易日，再按容量从最老的日期删。``keep_date`` 正在被计算，不删。"""
    root = Path(root)
    days = _date_dirs(root)
    for day in _expired_dirs(days):
        if day.name == str(keep_date):
            continue
        shutil.rmtree(day)
    limit = cache_limit_bytes()
    if limit is None:
        return
    while True:
        days = _date_dirs(root)
        total = sum(_dir_size(day) for day in days)
        if total <= limit:
            return
        victims = [day for day in days if day.name != str(keep_date)]
        if not victims:
            return
        shutil.rmtree(victims[0])


def _expired_dirs(days: list[Path]) -> list[Path]:
    """目录名早于上海今天减去保留天数的，算过期。"""
    max_days = cache_max_days()
    if max_days is None:
        return []
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    limit = (today - timedelta(days=max_days)).strftime("%Y%m%d")
    return [day for day in days if day.name < limit]


def _fetch(date: str, code: str, ftype: str) -> bytes | None:
    if _downloader is not None:
        return _downloader(date, code, ftype)
    from .baidu_books import download_book_bytes

    return download_book_bytes(date, code, ftype)


def _date_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    days = [
        child for child in root.iterdir()
        if child.is_dir() and len(child.name) == 8 and child.name.isdigit()
    ]
    return sorted(days, key=lambda item: item.name)


def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total
