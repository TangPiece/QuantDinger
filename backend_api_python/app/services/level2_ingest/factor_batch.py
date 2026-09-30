"""转换结束后，从 staging 明细批量计算日频因子并上传 R2。

数值口径用 ``level2_factors``，避免再留一份计算实现。测试可注入 loader 和 uploader。
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from app.services.level2_factors.daily import calc_daily_factors
from app.services.level2_factors.names import stored_columns

from . import config

# 没传 --workers 时，同一天并行的股票数。
DEFAULT_FACTOR_WORKERS = 8
# 进度按这个间隔打印，避免每一只股票都写一行日志。
_PROGRESS_EVERY = 100
_FILE_TYPES = ("行情", "逐笔成交", "逐笔委托")


def default_output_dir() -> Path:
    """批量因子写在 staging/factors，和图表本地缓存 level2_factors 分开。"""
    return config.STAGING_ROOT / "factors"


def list_book_codes(date: str, parquet_root: Path | None = None) -> list[str]:
    """列出当天三类明细都在的代码。"""
    day = Path(parquet_root or config.STAGING_PARQUET) / str(date)
    if not day.is_dir():
        return []
    codes = []
    for child in day.iterdir():
        if child.is_dir() and all((child / f"{ftype}.parquet").is_file() for ftype in _FILE_TYPES):
            codes.append(child.name)
    return sorted(codes)


def calc_symbol_parquet(date: str, code: str, parquet_root: str) -> dict | None:
    """子进程入口。从明细算出一行因子；缺文件或计算失败返回 None。"""
    try:
        frames = {}
        missing = 0
        root = Path(parquet_root)
        for ftype in _FILE_TYPES:
            path = root / str(date) / str(code) / f"{ftype}.parquet"
            if not path.is_file():
                frames[ftype] = pd.DataFrame()
                missing += 1
            else:
                frames[ftype] = pd.read_parquet(path)
        if missing == len(_FILE_TYPES):
            return None
        return calc_daily_factors(frames["行情"], frames["逐笔成交"], frames["逐笔委托"], code, date)
    except Exception:
        return None


def build_and_upload_dates(
    dates: list[str],
    *,
    workers: int = DEFAULT_FACTOR_WORKERS,
    parquet_root: Path | None = None,
    output_dir: Path | None = None,
    uploader=None,
    force: bool = False,
    rebuild_symbols: bool = False,
) -> bool:
    """按日期从早到晚计算并上传。某一天失败时继续其余日期，全部成功才返回 True。

    已完成且已上传的日期跳过。上传器用 ``(对象键, 字节)`` 调用；不传则写 R2。
    ``rebuild_symbols`` 只在全部日期都上传成功时，再把本地日文件收成股票镜像并上传。
    """
    ok = True
    destination_root = Path(output_dir or default_output_dir())
    books = Path(parquet_root) if parquet_root is not None else config.STAGING_PARQUET
    ordered = sorted({str(item) for item in dates})
    total_days = len(ordered)
    for index, date in enumerate(ordered, start=1):
        if not force and _is_done(destination_root, date) and _is_uploaded(destination_root, date):
            print(f"[{date}] {index}/{total_days} 因子已上传，跳过", flush=True)
            continue
        symbol_count = len(list_book_codes(date, books))
        print(f"[{date}] {index}/{total_days} 开始计算，共 {symbol_count} 只", flush=True)
        path = write_trade_date(
            date,
            destination_root,
            force=force,
            workers=workers,
            parquet_root=parquet_root,
        )
        if path is None:
            print(f"[{date}] 没有可算的明细", flush=True)
            ok = False
            continue
        try:
            print(f"[{date}] 正在上传 {config.factor_object_key(date)}", flush=True)
            _upload_factor_file(path, uploader)
        except Exception:
            print(f"[{date}] 因子上传失败", flush=True)
            ok = False
            continue
        if _is_done(destination_root, date):
            _mark_uploaded(destination_root, date)
        print(f"[{date}] 因子已上传 {config.factor_object_key(date)}", flush=True)
    if rebuild_symbols and ok:
        # 有一天失败就不重建镜像，避免用残缺的按日文件盖掉已有的股票历史。
        if not _rebuild_symbol_mirrors(destination_root):
            return False
    return ok


def _rebuild_symbol_mirrors(factors_dir: Path) -> bool:
    """按日宽表全部上传后再上传每只股票一份。只数对不上视为失败。"""
    from app.services.level2_factors.symbol_mirror import rebuild_symbol_mirrors

    print(f"正在从 {factors_dir} 重建股票镜像", flush=True)
    done, total = rebuild_symbol_mirrors(factors_dir)
    print(f"股票镜像已上传 {done}/{total}", flush=True)
    return bool(total) and done == total


def write_trade_date(
    date: str,
    output_dir: Path | None = None,
    *,
    source: str = "parquet",
    force: bool = False,
    loader=None,
    codes: list[str] | None = None,
    workers: int = 1,
    parquet_root: Path | None = None,
) -> Path | None:
    """计算一个交易日并原子写入 ``{date}.parquet``。没有股票时返回 None。

    不传 ``loader`` 时从 staging Parquet 读三类明细。``workers`` 大于 1 时同一天的股票并行。
    测试注入的 loader 仍在本进程顺序调用，避免把闭包送进子进程。
    """
    del source
    output_dir = Path(output_dir or default_output_dir())
    output_dir.mkdir(parents=True, exist_ok=True)
    if not force and _is_done(output_dir, date):
        return output_dir / f"{date}.parquet"
    books = Path(parquet_root) if parquet_root is not None else config.STAGING_PARQUET
    selected = list(codes) if codes is not None else list_book_codes(date, books)
    if not selected:
        return None

    if loader is None:
        rows, errors = _rows_from_parquet(date, selected, books, max(1, int(workers)))
    else:
        rows, errors = _rows_from_loader(date, selected, loader)

    if not rows:
        return None

    # 只落基础列。5/10/20 日滚动值在图表和回测读取时现算，避免把它们写进每天的全市场文件。
    today = pd.DataFrame(rows)
    columns = stored_columns()
    for column in columns:
        if column not in today.columns:
            today[column] = float("nan")
    panel = today[columns]
    destination = output_dir / f"{date}.parquet"
    temporary = output_dir / f".{date}.parquet.tmp"
    print(f"[{date}] 正在写入 {destination.name}，{len(panel)} 行", flush=True)
    panel.to_parquet(temporary, index=False)
    temporary.replace(destination)
    if errors == 0:
        _mark_done(output_dir, date, rows=len(panel))
    return destination


def _done_path(output_dir: Path, date: str) -> Path:
    return output_dir / "_done" / f"{date}.json"


def _is_done(output_dir: Path, date: str) -> bool:
    return _done_path(output_dir, date).is_file() and (output_dir / f"{date}.parquet").is_file()


def _mark_done(output_dir: Path, date: str, *, rows: int) -> None:
    path = _done_path(output_dir, date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": date, "rows": rows}, ensure_ascii=False), encoding="utf-8")


def _rows_from_loader(date: str, codes: list[str], loader) -> tuple[list[dict], int]:
    """测试注入的读取函数，保持顺序计算。"""
    rows = []
    errors = 0
    for code in codes:
        frames = {}
        missing = 0
        failed = False
        for ftype in _FILE_TYPES:
            try:
                frames[ftype] = loader(date, code, ftype, "parquet")
            except FileNotFoundError:
                frames[ftype] = pd.DataFrame()
                missing += 1
            except Exception:
                errors += 1
                failed = True
                break
        if failed or missing == len(_FILE_TYPES):
            continue
        try:
            rows.append(calc_daily_factors(frames["行情"], frames["逐笔成交"], frames["逐笔委托"], code, date))
        except Exception:
            errors += 1
    return rows, errors


def _emit_symbol_progress(date: str, done: int, total: int) -> None:
    """每完成一批股票打印一次，最后一只也打印。"""
    if total <= 0:
        return
    if done == total or done % _PROGRESS_EVERY == 0:
        print(f"[{date}] 已完成 {done}/{total}", flush=True)


def _rows_from_parquet(date: str, codes: list[str], books: Path, workers: int) -> tuple[list[dict], int]:
    """同一天的股票并行读 Parquet。返回成功的行和失败数。"""
    total = len(codes)
    if workers <= 1 or total <= 1:
        rows = []
        errors = 0
        for done, code in enumerate(codes, start=1):
            row = calc_symbol_parquet(date, code, str(books))
            if row is None:
                errors += 1
            else:
                rows.append(row)
            _emit_symbol_progress(date, done, total)
        return rows, errors
    rows = []
    errors = 0
    done = 0
    with ProcessPoolExecutor(max_workers=min(workers, total)) as pool:
        futures = [pool.submit(calc_symbol_parquet, date, code, str(books)) for code in codes]
        for future in futures:
            done += 1
            try:
                row = future.result()
            except Exception:
                errors += 1
                _emit_symbol_progress(date, done, total)
                continue
            if row is None:
                errors += 1
            else:
                rows.append(row)
            _emit_symbol_progress(date, done, total)
    return rows, errors


def _upload_factor_file(path: Path, uploader) -> None:
    """上传一整天的因子文件。没注入上传器时走 R2，失败会抛出。"""
    payload = path.read_bytes()
    key = config.factor_object_key(path.stem)
    if uploader is not None:
        uploader(key, payload)
        return
    from .r2_client import upload_bytes

    upload_bytes(key, payload)


def _uploaded_path(output_dir: Path, date: str) -> Path:
    return output_dir / "_uploaded" / f"{date}.json"


def _is_uploaded(output_dir: Path, date: str) -> bool:
    return _uploaded_path(output_dir, date).is_file()


def _mark_uploaded(output_dir: Path, date: str) -> None:
    path = _uploaded_path(output_dir, date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"date": date, "key": config.factor_object_key(date)}, ensure_ascii=False),
        encoding="utf-8",
    )


def list_staging_dates(parquet_root: Path | None = None) -> list[str]:
    """列出 staging 明细里已有的交易日，从早到晚。"""
    root = Path(parquet_root or config.STAGING_PARQUET)
    if not root.is_dir():
        return []
    return sorted(
        child.name
        for child in root.iterdir()
        if child.is_dir() and len(child.name) == 8 and child.name.isdigit()
    )


def main(argv: list[str] | None = None) -> int:
    """只读已转换的 Parquet 计算因子并上传。不重新解压或转 CSV。

    ``--dry-run`` 只打印将要处理的日期。指定 ``--dates`` 时仍按从早到晚上传。
    """
    parser = argparse.ArgumentParser(description="从 level2_staging/parquet 计算日频因子并上传 R2")
    parser.add_argument("--dates", nargs="*", help="只算这些 YYYYMMDD，默认全部已有交易日")
    parser.add_argument("--workers", type=int, default=DEFAULT_FACTOR_WORKERS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="已上传的日期也重算；未指定日期时接着重建股票镜像")
    args = parser.parse_args(argv)

    available = list_staging_dates()
    if args.dates:
        wanted = [str(item) for item in args.dates]
        missing = sorted(set(wanted) - set(available))
        if missing:
            print(f"staging 里没有这些日期: {missing}", flush=True)
            return 1
        dates = sorted(set(wanted))
    else:
        dates = available

    print(f"因子日期 {dates}", flush=True)
    if args.dry_run:
        return 0
    if not dates:
        print(f"没有可算的明细: {config.STAGING_PARQUET}", flush=True)
        return 1
    # 只在整批强制重算时重建镜像。单日 --force 只覆盖那一天的宽表。
    rebuild_symbols = bool(args.force) and not args.dates
    ok = build_and_upload_dates(
        dates,
        workers=max(1, int(args.workers)),
        force=args.force,
        rebuild_symbols=rebuild_symbols,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
