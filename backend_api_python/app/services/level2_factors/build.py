"""按交易日从 Parquet 明细计算因子面板。

命令::

    python -m app.services.level2_factors.build --dates 20251103 --parquet-dir /path/to/parquet

不读取 CSV。本地没有的明细从百度网盘补齐。缺文件的标的跳过。已完成且写过清单的日期默认跳过。
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.level2_factor_panel import canonical_symbol, panel_directory

from .book import (
    default_parquet_directory,
    download_books,
    enforce_book_cache,
    list_equity_codes,
    list_remote_equity_codes,
    load_book,
)
from .daily import calc_daily_factors
from .names import BASE_FACTORS, stored_columns

# 同一只股票同时向网盘要的交易日数。再大容易把百度接口打满。
DOWNLOAD_WORKERS = 8
_log = logging.getLogger(__name__)
_fill_guard = threading.Lock()
_filling: set[str] = set()
_filled: set[tuple[str, str]] = set()


def write_trade_date(
    date: str,
    parquet_dir: Path,
    output_dir: Path,
    *,
    force: bool = False,
    codes: list[str] | None = None,
) -> Path | None:
    """计算一个交易日并写入 ``{date}.parquet``。没有股票时返回 None。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not force and _is_done(output_dir, date):
        return output_dir / f"{date}.parquet"

    if codes is not None:
        selected = list(codes)
    else:
        selected = list_equity_codes(parquet_dir, date)
        # 当天本地还没有目录时，代码列表以网盘为准，缺的文件在读取时再下载。
        if not selected:
            selected = list_remote_equity_codes(date)
    rows = []
    errors = 0
    for code in selected:
        try:
            frames = load_book(parquet_dir, date, code)
        except FileNotFoundError:
            continue
        except Exception:
            errors += 1
            continue
        try:
            rows.append(
                calc_daily_factors(
                    frames["行情"],
                    frames["逐笔成交"],
                    frames["逐笔委托"],
                    code,
                    date,
                )
            )
        except Exception:
            errors += 1

    if not rows:
        return None

    # 日文件只保留基础因子。滚动列由读取端按股票序列现算。
    today = pd.DataFrame(rows)
    columns = stored_columns()
    for column in columns:
        if column not in today.columns:
            today[column] = float("nan")
    panel = today[columns]
    destination = output_dir / f"{date}.parquet"
    temporary = output_dir / f".{date}.parquet.tmp"
    panel.to_parquet(temporary, index=False)
    temporary.replace(destination)
    from .factor_cache import publish_factor_file

    publish_factor_file(destination)
    if errors == 0:
        _mark_done(output_dir, date, rows=len(panel))
    return destination


def recent_weekdays(today=None, span_days: int = 365) -> list[str]:
    """上海今天往前 ``span_days`` 天里的工作日，不含周末。节假日留给下载时跳过。"""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    current = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    start = current - timedelta(days=span_days)
    dates = []
    day = start
    while day <= current:
        if day.weekday() < 5:
            dates.append(day.strftime("%Y%m%d"))
        day += timedelta(days=1)
    return dates


def ensure_symbol(
    symbol: str,
    dates: list[str],
    *,
    parquet_dir: Path | None = None,
    store: Any | None = None,
) -> list[str]:
    """先下完这只股票的明细，再从早到晚计算并覆盖写入日频 Parquet。

    返回已经处理完的交易日。网盘没有的日子算处理完。下载或计算失败的日子不返回，下次还能再补。
    """
    code = canonical_symbol(symbol)
    selected = sorted({str(item) for item in dates if str(item).isdigit() and len(str(item)) == 8})
    if not code or not selected:
        return []
    books = Path(parquet_dir) if parquet_dir is not None else default_parquet_directory()
    books.mkdir(parents=True, exist_ok=True)
    # 两个 gunicorn worker 都会收到选因子请求。文件锁保证同一只股票只有一路在下。
    lock_path = books / f".{code}.fill.lock"
    with lock_path.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            return _fill_dates(code, selected, books, store)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _fill_dates(code: str, selected: list[str], books: Path, store: Any | None) -> list[str]:
    """缺的交易日并行落下，全部下完再从早到晚计算。``handled`` 里才是可以不再重试的日期。"""
    cache = store if store is not None else _factor_store()
    handled: list[str] = []
    pending: list[str] = []
    _log.info("Level2 开始补 %s，共 %s 个工作日", code, len(selected))
    for date in selected:
        if cache.has(code, date) or _books_ready(books, date, code):
            continue
        pending.append(date)
    _download_pending(code, pending, books, handled)
    # 一年跨度下完再按容量和保留天数收一次，避免下到一半删掉更早的日子。
    enforce_book_cache(books, keep_date=selected[-1])
    for date in selected:
        if cache.has(code, date):
            # 因子已经在本地或 R2，项目目录里的明细不再保留。
            discard_symbol_books(books, date, code)
            handled.append(date)
            continue
        if date in handled or not _books_ready(books, date, code):
            continue
        factors = _factor_row(date, code, books, cache)
        if factors is None:
            continue
        cache.upsert(code, date, factors)
        discard_symbol_books(books, date, code)
        handled.append(date)
    return handled


def _download_pending(code: str, pending: list[str], books: Path, handled: list[str]) -> None:
    """最多 ``DOWNLOAD_WORKERS`` 路同时下。某一天失败不影响其余日期。"""
    if not pending:
        return
    workers = min(DOWNLOAD_WORKERS, len(pending))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download_books, books, date, code): date for date in pending}
        for future in as_completed(futures):
            date = futures[future]
            try:
                future.result()
            except FileNotFoundError:
                _log.info("Level2 明细不存在，跳过 %s %s", date, code)
                handled.append(date)
            except Exception:
                _log.warning("Level2 明细下载失败 %s %s", date, code, exc_info=True)


def schedule_symbol_fill(symbol: str, dates: list[str] | None = None) -> bool:
    """后台补一只股票近一年工作日。正在补时返回 True；没有新日期时返回 False。"""
    code = canonical_symbol(symbol)
    # 图表窗口只有几个月。补数范围改用近一年，不看传入的 K 线日期。
    del dates
    pending = recent_weekdays()
    if not code or not pending:
        return False
    with _fill_guard:
        if code in _filling:
            return True
        pending = [date for date in sorted(set(pending)) if (code, date) not in _filled]
        if not pending:
            return False
        _filling.add(code)
    worker = threading.Thread(
        target=_fill_worker,
        args=(code, pending),
        name=f"level2-fill-{code}",
        daemon=True,
    )
    worker.start()
    return True


def _fill_worker(code: str, dates: list[str]) -> None:
    handled: list[str] = []
    try:
        handled = ensure_symbol(code, dates)
    except Exception:
        _log.warning("Level2 补数失败 %s", code, exc_info=True)
    finally:
        # 只记下真正补完的日期。中断后重选因子会从缺的那一天接着下。
        with _fill_guard:
            _filled.update((code, date) for date in handled)
            _filling.discard(code)


def _factor_store():
    from .factor_cache import get_factor_cache

    return get_factor_cache()


def _factor_row(date: str, code: str, parquet_dir: Path, cache) -> dict | None:
    """计算一只股票当天的基础因子。滚动列不写进日文件，留给读取时现算。"""
    del cache
    try:
        frames = load_book(parquet_dir, date, code)
        row = calc_daily_factors(frames["行情"], frames["逐笔成交"], frames["逐笔委托"], code, date)
    except Exception:
        _log.warning("Level2 单标的计算失败 %s %s", date, code, exc_info=True)
        return None
    return {column: row.get(column, float("nan")) for column in BASE_FACTORS}


def _books_ready(root: Path, date: str, code: str) -> bool:
    from .book import ready_book_root

    return ready_book_root(root, date, code) is not None


def discard_symbol_books(root: Path, date: str, code: str) -> None:
    """算完后清项目缓存。具体删除规则在 ``book.discard_symbol_books``。"""
    from .book import discard_symbol_books as drop_books

    drop_books(root, date, code)


def _done_path(output_dir: Path, date: str) -> Path:
    return output_dir / "_done" / f"{date}.json"


def _is_done(output_dir: Path, date: str) -> bool:
    return _done_path(output_dir, date).is_file() and (output_dir / f"{date}.parquet").is_file()


def _mark_done(output_dir: Path, date: str, *, rows: int) -> None:
    path = _done_path(output_dir, date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": date, "rows": rows}, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    """命令行入口。``--parquet-dir`` 优先；都空则用项目内 ``data/level2_parquet``。"""
    parser = argparse.ArgumentParser(description="从 Level2 Parquet 计算日频因子")
    parser.add_argument("--dates", required=True, help="交易日，逗号分隔，如 20251103,20251104")
    parser.add_argument("--parquet-dir", default="", help="明细 Parquet 根目录，默认 data/level2_parquet")
    parser.add_argument("--output", default="", help="因子面板目录，默认 LEVEL2_FACTOR_PANEL_DIR")
    parser.add_argument("--force", action="store_true", help="忽略完成标记并重算")
    args = parser.parse_args(argv)
    raw_dir = args.parquet_dir or os.getenv("LEVEL2_PARQUET_DIR", "").strip()
    if raw_dir:
        parquet_dir = Path(raw_dir)
        parquet_dir.mkdir(parents=True, exist_ok=True)
    else:
        parquet_dir = default_parquet_directory()
    output = Path(args.output) if args.output else panel_directory()
    if output is None:
        raise SystemExit("需要 --output 或环境变量 LEVEL2_FACTOR_PANEL_DIR")
    dates = [item.strip() for item in str(args.dates).split(",") if item.strip()]
    for date in dates:
        path = write_trade_date(date, parquet_dir, output, force=args.force)
        if path is None:
            print(f"[{date}] 没有可写的 A 股 Parquet", flush=True)
        else:
            print(f"[{date}] {path}", flush=True)


if __name__ == "__main__":
    main()
