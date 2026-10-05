"""从本地明细批量计算日频因子并写入 D1。

可读 staging Parquet 或已解压 CSV。数值口径用 ``level2_factors``，避免再留一份计算实现。
测试可注入 loader 和 uploader。
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
from .symbols import is_default_symbol

# 没传 --workers 时，同一天并行的股票数。
DEFAULT_FACTOR_WORKERS = 8
# 进度按这个间隔打印，避免每一只股票都写一行日志。
_PROGRESS_EVERY = 100
_FILE_TYPES = ("行情", "逐笔成交", "逐笔委托")


def default_output_dir() -> Path:
    """批量因子断点与临时日文件目录；发布后日宽表会删，真源在 D1。"""
    return config.STAGING_ROOT / "factors"


def list_book_codes(date: str, parquet_root: Path | None = None) -> list[str]:
    """列出当天三类 Parquet 明细都在的代码。"""
    day = Path(parquet_root or config.STAGING_PARQUET) / str(date)
    if not day.is_dir():
        return []
    codes = []
    for child in day.iterdir():
        if child.is_dir() and all((child / f"{ftype}.parquet").is_file() for ftype in _FILE_TYPES):
            codes.append(child.name)
    return sorted(codes)


def list_csv_codes(
    date: str,
    csv_root: Path | None = None,
    *,
    equities_only: bool = True,
) -> list[str]:
    """列出当天三类 CSV 明细都在的代码；默认只保留 A 股与场内基金。"""
    day = Path(csv_root or config.DATA_ROOT) / str(date)
    if not day.is_dir():
        return []
    codes = []
    for child in day.iterdir():
        if not child.is_dir():
            continue
        code = child.name
        if equities_only and not is_default_symbol(code):
            continue
        if all((child / f"{ftype}.csv").is_file() for ftype in _FILE_TYPES):
            codes.append(code)
    return sorted(codes)


def calc_symbol_parquet(date: str, code: str, parquet_root: str) -> dict | None:
    """子进程入口。从 Parquet 明细算出一行因子；缺文件或计算失败返回 None。"""
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


def calc_symbol_csv(date: str, code: str, csv_root: str) -> dict | None:
    """子进程入口。从已解压 CSV 算出一行因子；缺文件或计算失败返回 None。"""
    try:
        from .csv_to_parquet import read_csv_bytes

        frames = {}
        missing = 0
        root = Path(csv_root)
        for ftype in _FILE_TYPES:
            path = root / str(date) / str(code) / f"{ftype}.csv"
            if not path.is_file():
                frames[ftype] = pd.DataFrame()
                missing += 1
            else:
                frames[ftype] = read_csv_bytes(path.read_bytes(), ftype)
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
    csv_root: Path | None = None,
    source: str = "parquet",
    equities_only: bool = True,
    output_dir: Path | None = None,
    uploader=None,
    force: bool = False,
    rebuild_symbols: bool = False,
) -> bool:
    """按日期从早到晚计算并上传。某一天失败时继续其余日期，全部成功才返回 True。

    ``source`` 为 ``parquet``（staging 明细）或 ``csv``（已解压目录）。
    已完成且已写入 D1 的日期跳过。上传器用 ``(对象键, 字节)`` 调用（测试）；不传则写 D1。
    ``rebuild_symbols`` 只在全部日期都上传成功时，再把本地日文件收成股票镜像并上传。
    """
    ok = True
    destination_root = Path(output_dir or default_output_dir())
    kind = str(source or "parquet").strip().lower()
    books = Path(parquet_root) if parquet_root is not None else config.STAGING_PARQUET
    raw = Path(csv_root) if csv_root is not None else config.DATA_ROOT
    ordered = sorted({str(item) for item in dates})
    total_days = len(ordered)
    for index, date in enumerate(ordered, start=1):
        if not force and _is_done(destination_root, date) and _is_uploaded(destination_root, date):
            print(f"[{date}] {index}/{total_days} 因子已写入 D1，跳过", flush=True)
            continue
        if kind == "csv":
            symbol_count = len(list_csv_codes(date, raw, equities_only=equities_only))
        else:
            symbol_count = len(list_book_codes(date, books))
        print(f"[{date}] {index}/{total_days} 开始计算，共 {symbol_count} 只", flush=True)
        path = write_trade_date(
            date,
            destination_root,
            source=kind,
            force=force,
            workers=workers,
            parquet_root=parquet_root,
            csv_root=csv_root,
            equities_only=equities_only,
        )
        if path is None:
            print(f"[{date}] 没有可算的明细", flush=True)
            ok = False
            continue
        try:
            print(f"[{date}] 正在写入 D1 l2_factors", flush=True)
            _upload_factor_file(path, uploader)
        except Exception:
            print(f"[{date}] 因子写入 D1 失败", flush=True)
            ok = False
            continue
        if _is_done(destination_root, date):
            _mark_uploaded(destination_root, date)
        print(f"[{date}] 因子已写入 D1", flush=True)
    if rebuild_symbols and ok:
        # 有一天失败就不重建镜像，避免用残缺的按日文件盖掉已有的股票历史。
        if not _rebuild_symbol_mirrors(destination_root):
            return False
    return ok


def _rebuild_symbol_mirrors(factors_dir: Path) -> bool:
    """D1 模式下股票镜像为 no-op；若仍走旧上传则只数对不上视为失败。"""
    from app.services.level2_factors.symbol_mirror import rebuild_symbol_mirrors

    print(f"正在检查股票镜像 {factors_dir}", flush=True)
    done, total = rebuild_symbol_mirrors(factors_dir)
    if total == 0:
        # D1 已按 symbol 索引，跳过视为成功。
        return True
    print(f"股票镜像已上传 {done}/{total}", flush=True)
    return done == total


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
    csv_root: Path | None = None,
    equities_only: bool = True,
) -> Path | None:
    """计算一个交易日并原子写入 ``{date}.parquet``。没有股票时返回 None。

    ``source`` 为 ``parquet``（staging）或 ``csv``（已解压目录）。不传 ``loader`` 时按
    source 读三类明细。``workers`` 大于 1 时同一天的股票并行。测试注入的 loader 仍在
    本进程顺序调用，避免把闭包送进子进程。
    """
    kind = str(source or "parquet").strip().lower()
    if kind not in {"parquet", "csv"}:
        raise ValueError(f"不支持的 source: {source}")
    output_dir = Path(output_dir or default_output_dir())
    output_dir.mkdir(parents=True, exist_ok=True)
    # 已有标记且日文件还在时才能直接复用；日文件发布后会删，未上传则重算。
    if not force and _is_done(output_dir, date):
        existing = output_dir / f"{date}.parquet"
        if existing.is_file():
            return existing
    books = Path(parquet_root) if parquet_root is not None else config.STAGING_PARQUET
    raw = Path(csv_root) if csv_root is not None else config.DATA_ROOT
    if codes is not None:
        selected = list(codes)
    elif kind == "csv":
        selected = list_csv_codes(date, raw, equities_only=equities_only)
    else:
        selected = list_book_codes(date, books)
    if not selected:
        return None

    if loader is not None:
        rows, errors = _rows_from_loader(date, selected, loader)
    elif kind == "csv":
        rows, errors = _rows_from_csv(date, selected, raw, max(1, int(workers)))
    else:
        rows, errors = _rows_from_parquet(date, selected, books, max(1, int(workers)))

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
    """只看断点标记；日 parquet 发布到 D1 后会被删掉。"""
    return _done_path(output_dir, date).is_file()


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
    return _rows_from_worker(date, codes, str(books), workers, calc_symbol_parquet)


def _rows_from_csv(date: str, codes: list[str], csv_root: Path, workers: int) -> tuple[list[dict], int]:
    """同一天的股票并行读 CSV。返回成功的行和失败数。"""
    return _rows_from_worker(date, codes, str(csv_root), workers, calc_symbol_csv)


def _rows_from_worker(
    date: str,
    codes: list[str],
    root: str,
    workers: int,
    worker,
) -> tuple[list[dict], int]:
    """按股票并行调用子进程入口，汇总成功行与失败数。"""
    total = len(codes)
    if workers <= 1 or total <= 1:
        rows = []
        errors = 0
        for done, code in enumerate(codes, start=1):
            row = worker(date, code, root)
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
        futures = [pool.submit(worker, date, code, root) for code in codes]
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
    """把一日因子发布到远端。没注入上传器时写入 D1（经 Worker），失败会抛出。

    D1 成功后删除本地日 parquet，只保留 ``_done`` / ``_uploaded`` 标记。
    """
    if uploader is not None:
        # 测试可注入旧的「对象键 + bytes」上传器。
        payload = path.read_bytes()
        key = config.factor_object_key(path.stem)
        uploader(key, payload)
        return
    from app.services.level2_factors import d1_factors

    d1_factors.upsert_day(path.stem, path)
    path.unlink(missing_ok=True)


def _uploaded_path(output_dir: Path, date: str) -> Path:
    return output_dir / "_uploaded" / f"{date}.json"


def _is_uploaded(output_dir: Path, date: str) -> bool:
    return _uploaded_path(output_dir, date).is_file()


def _mark_uploaded(output_dir: Path, date: str) -> None:
    path = _uploaded_path(output_dir, date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"date": date, "target": "d1", "table": "l2_factors"}, ensure_ascii=False),
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
    parser = argparse.ArgumentParser(description="从 level2_staging/parquet 计算日频因子并写入 D1")
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
