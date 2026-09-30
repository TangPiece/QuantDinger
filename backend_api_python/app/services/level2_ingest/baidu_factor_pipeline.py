"""从百度网盘按日下载 Level2 明细，算因子并上传 R2。

按日历日从早到晚串行：先并行下完该日全部股票，再本地计算日宽表并上传；
上传成功后删除当日本地明细，再进入下一日。已上传日期默认跳过，可断点续跑。
"""
from __future__ import annotations

import argparse
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

from app.services.level2_factors.book import (
    default_parquet_directory,
    discard_symbol_books,
    download_books,
    list_remote_equity_codes,
)

from . import config, factor_batch

# 百度接口并发不宜过大，默认与图表补数下载一致。
DEFAULT_DOWNLOAD_WORKERS = 8
_PROGRESS_EVERY = 100


class UploadFailed(Exception):
    """当日因子上传失败，调用方应停止后续日期。"""


def iter_calendar_dates(start: str, end: str) -> list[str]:
    """闭区间按日历日从早到晚，含周末。起止须为 YYYYMMDD。"""
    begin = _parse_day(start)
    finish = _parse_day(end)
    if begin > finish:
        raise ValueError(f"起始日不能晚于结束日: {start} > {end}")
    days: list[str] = []
    current = begin
    while current <= finish:
        days.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return days


def process_date(
    date: str,
    *,
    books_dir: Path,
    output_dir: Path,
    download_workers: int = DEFAULT_DOWNLOAD_WORKERS,
    workers: int = factor_batch.DEFAULT_FACTOR_WORKERS,
    force: bool = False,
    uploader=None,
) -> str:
    """处理一个交易日。

    返回 ``skipped`` / ``empty`` / ``ok`` / ``failed``。
    上传失败抛异常，由调用方停止后续日期。
    """
    day = str(date).strip()
    if not force and factor_batch._is_done(output_dir, day) and factor_batch._is_uploaded(output_dir, day):
        print(f"[{day}] 因子已上传，跳过", flush=True)
        return "skipped"

    codes = list_remote_equity_codes(day)
    if not codes:
        print(f"[{day}] 网盘无 A 股目录，跳过", flush=True)
        return "empty"

    print(f"[{day}] 开始下载，共 {len(codes)} 只，workers={max(1, int(download_workers))}", flush=True)
    downloaded = _download_all_codes(
        day,
        codes,
        books_dir,
        max(1, int(download_workers)),
    )
    print(f"[{day}] 下载结束，成功 {downloaded}/{len(codes)}", flush=True)

    print(f"[{day}] 开始计算因子，workers={max(1, int(workers))}", flush=True)
    path = factor_batch.write_trade_date(
        day,
        output_dir,
        force=True,
        workers=max(1, int(workers)),
        parquet_root=books_dir,
    )
    if path is None:
        print(f"[{day}] 没有可算的明细", flush=True)
        return "failed"

    print(f"[{day}] 正在上传 {config.factor_object_key(day)}", flush=True)
    try:
        factor_batch._upload_factor_file(path, uploader)
    except Exception as exc:
        # 保留本地明细和日宽表，便于下次重试；不再进下一日。
        raise UploadFailed(day) from exc
    # 有成功行就落了日文件；上传成功后一律记上传标记，便于断点续跑。
    if not factor_batch._is_done(output_dir, day):
        factor_batch._mark_done(output_dir, day, rows=_row_count(path))
    factor_batch._mark_uploaded(output_dir, day)
    _cleanup_day_books(books_dir, day)
    print(f"[{day}] 因子已上传 {config.factor_object_key(day)}，本地明细已清理", flush=True)
    return "ok"


def run_range(
    start: str,
    end: str,
    *,
    books_dir: Path | None = None,
    output_dir: Path | None = None,
    download_workers: int = DEFAULT_DOWNLOAD_WORKERS,
    workers: int = factor_batch.DEFAULT_FACTOR_WORKERS,
    force: bool = False,
    dry_run: bool = False,
    mirror: bool = False,
    uploader=None,
) -> bool:
    """按日串行跑完区间。上传失败立即停止；其余失败继续，全部成功才返回 True。"""
    dates = iter_calendar_dates(start, end)
    books = Path(books_dir) if books_dir is not None else default_parquet_directory()
    books.mkdir(parents=True, exist_ok=True)
    destination = Path(output_dir) if output_dir is not None else factor_batch.default_output_dir()
    destination.mkdir(parents=True, exist_ok=True)

    print(f"日期 {start}..{end} 共 {len(dates)} 天 books={books} factors={destination}", flush=True)
    if dry_run:
        for day in dates:
            print(day, flush=True)
        return True

    ok = True
    for index, day in enumerate(dates, start=1):
        print(f"==== {index}/{len(dates)} {day} ====", flush=True)
        try:
            status = process_date(
                day,
                books_dir=books,
                output_dir=destination,
                download_workers=download_workers,
                workers=workers,
                force=force,
                uploader=uploader,
            )
        except UploadFailed:
            print(f"[{day}] 因子上传失败，停止后续日期", flush=True)
            return False
        if status == "failed":
            ok = False

    if mirror and ok:
        if not factor_batch._rebuild_symbol_mirrors(destination):
            return False
    return ok


def _download_all_codes(date: str, codes: list[str], books_dir: Path, workers: int) -> int:
    """并行下载；单股失败不中断。返回成功只数。"""
    total = len(codes)
    if total == 0:
        return 0
    success = 0
    done = 0
    with ThreadPoolExecutor(max_workers=min(workers, total)) as pool:
        futures = {pool.submit(download_books, books_dir, date, code): code for code in codes}
        for future in as_completed(futures):
            code = futures[future]
            done += 1
            try:
                future.result()
                success += 1
            except FileNotFoundError:
                print(f"[{date}] 明细不存在，跳过 {code}", flush=True)
            except Exception as exc:
                print(f"[{date}] 下载失败 {code}: {exc}", flush=True)
            if done == total or done % _PROGRESS_EVERY == 0:
                print(f"[{date}] 下载进度 {done}/{total}", flush=True)
    return success


def _cleanup_day_books(books_dir: Path, date: str) -> None:
    """删除项目缓存里这一天的全部明细目录。"""
    day_dir = Path(books_dir) / str(date)
    if not day_dir.exists():
        return
    try:
        resolved = day_dir.resolve()
        root_resolved = Path(books_dir).resolve()
    except OSError:
        return
    if root_resolved not in resolved.parents and resolved != root_resolved:
        return
    if resolved == root_resolved:
        return
    # 优先整日删除；若权限等问题再退回逐股 discard。
    try:
        shutil.rmtree(resolved)
        return
    except OSError:
        pass
    if not day_dir.is_dir():
        return
    for child in list(day_dir.iterdir()):
        if child.is_dir():
            discard_symbol_books(books_dir, date, child.name)


def _row_count(path: Path) -> int:
    try:
        import pandas as pd

        return int(len(pd.read_parquet(path)))
    except Exception:
        return 0


def _parse_day(value: str):
    text = str(value).strip()
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"日期须为 YYYYMMDD，收到: {value!r}")
    return datetime.strptime(text, "%Y%m%d").date()


def main(argv: list[str] | None = None) -> int:
    """命令行入口：``--start`` / ``--end`` 闭区间，先下载后算因子再上传。"""
    parser = argparse.ArgumentParser(description="从百度网盘按日下载明细、计算因子并上传 R2")
    parser.add_argument("--start", required=True, help="起始交易日 YYYYMMDD")
    parser.add_argument("--end", required=True, help="结束交易日 YYYYMMDD")
    parser.add_argument("--download-workers", type=int, default=DEFAULT_DOWNLOAD_WORKERS)
    parser.add_argument("--workers", type=int, default=factor_batch.DEFAULT_FACTOR_WORKERS, help="因子计算并行度")
    parser.add_argument("--force", action="store_true", help="已上传的日期也重算并覆盖上传")
    parser.add_argument("--dry-run", action="store_true", help="只打印将处理的日历日")
    parser.add_argument("--mirror", action="store_true", help="全部日期成功后再重建股票镜像")
    parser.add_argument("--books-dir", default="", help="明细临时目录，默认 data/level2_parquet")
    parser.add_argument("--output", default="", help="因子输出目录，默认 staging/factors")
    args = parser.parse_args(argv)

    books = Path(args.books_dir) if args.books_dir else None
    output = Path(args.output) if args.output else None
    ok = run_range(
        args.start,
        args.end,
        books_dir=books,
        output_dir=output,
        download_workers=max(1, int(args.download_workers)),
        workers=max(1, int(args.workers)),
        force=args.force,
        dry_run=args.dry_run,
        mirror=args.mirror,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
