"""按日全量：解压后直接从 CSV 算日频因子并写入 D1（不落明细 Parquet）。

阶段 A：先处理所有已解压 local 目录；未达标则停止，不解压任何新 7z。
阶段 B：对剩余 .7z 逐日「整包解压 → 算因子 → 写 D1 → 达标删 CSV+.7z → 再解下一包」。
解压落点为 config.DATA_ROOT（默认 data/level2_raw/{date}/）。
"""
from __future__ import annotations

import argparse
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import build_manifest, config, extract, factor_batch
from .convert_local import _format_elapsed, delete_sources

# 对齐原转换门槛（约三千标的 × 3 文件 ≈ 10000）：日宽表至少这么多行才允许删源。
_MIN_FACTOR_ROWS = 3_000


def _discover_local_dates(only: list[str] | None = None) -> list[str]:
    """扫描已解压目录 DATA_ROOT/{date}/。"""
    if not config.DATA_ROOT.is_dir():
        return []
    dates = sorted(
        p.name for p in config.DATA_ROOT.iterdir()
        if p.is_dir() and p.name.isdigit() and len(p.name) == 8
    )
    if only:
        dates = [d for d in dates if d in set(only)]
    return dates


def _discover_7z_dates(only: list[str] | None = None) -> list[str]:
    """扫描 DATA_ROOT/*.7z。"""
    if not config.DATA_ROOT.is_dir():
        dates: list[str] = []
    else:
        dates = sorted(p.stem for p in config.DATA_ROOT.glob("*.7z"))
    if only:
        wanted = set(only)
        missing = wanted - set(dates)
        if missing:
            raise FileNotFoundError(f"找不到归档: {sorted(missing)}")
        dates = [d for d in dates if d in wanted]
    return dates


def _can_delete_after_factors(stats: dict) -> tuple[bool, str]:
    """因子写入成功且行数达标时才允许删源。"""
    if not stats.get("uploaded"):
        return False, "not_uploaded"
    rows = int(stats.get("rows") or 0)
    if rows < _MIN_FACTOR_ROWS:
        return False, f"rows={rows} < {_MIN_FACTOR_ROWS}"
    return True, "ok"


def _row_count(path: Path | None) -> int:
    """日宽表行数；文件不存在时为 0。"""
    if path is None or not path.is_file():
        return 0
    return int(len(pd.read_parquet(path)))


def _process_day(
    date: str,
    *,
    source: str,
    delete: bool,
    dry_run: bool,
    skip_existing: bool,
    equities_only: bool,
    workers: int | None,
    force_extract: bool,
) -> dict:
    """单日闭环：可选解压 → CSV 算因子 → 写 D1 → 达标删源。"""
    output_dir = factor_batch.default_output_dir()
    n_workers = max(1, workers if workers is not None else factor_batch.DEFAULT_FACTOR_WORKERS)

    if skip_existing and factor_batch._is_uploaded(output_dir, date):
        print(f"[{date}] 因子已写入 D1，跳过", flush=True)
        return {
            "date": date,
            "source": source,
            "stats": {"rows": 0, "symbols": 0, "uploaded": True, "skipped": True},
            "ok": True,
            "reason": "already_uploaded",
        }

    if dry_run:
        symbols = factor_batch.list_csv_codes(date, config.DATA_ROOT, equities_only=equities_only)
        print(f"[{date}] dry-run source={source} symbols={len(symbols)}", flush=True)
        return {
            "date": date,
            "source": source,
            "stats": {"rows": 0, "symbols": len(symbols), "uploaded": False, "skipped": False},
            "ok": True,
            "reason": "dry_run",
        }

    if force_extract:
        seven_z = config.DATA_ROOT / f"{date}.7z"
        if not seven_z.is_file():
            raise FileNotFoundError(seven_z)
        if not config.local_manifest_path(date).exists():
            print(f"[{date}] 生成 manifest（仅此一次 tar -tf）", flush=True)
            build_manifest.build(date)
        print(f"[{date}] 整包解压 → {config.DATA_ROOT} {seven_z}", flush=True)
        extract.extract_archive(seven_z)

    day_dir = config.DATA_ROOT / date
    if not day_dir.is_dir():
        raise FileNotFoundError(f"未找到已解压目录: {day_dir}")

    symbols = factor_batch.list_csv_codes(date, config.DATA_ROOT, equities_only=equities_only)
    print(f"[{date}] 开始从 CSV 计算因子，共 {len(symbols)} 只 workers={n_workers}", flush=True)
    t0 = time.perf_counter()
    path = factor_batch.write_trade_date(
        date,
        output_dir,
        source="csv",
        csv_root=config.DATA_ROOT,
        force=not skip_existing,
        workers=n_workers,
        equities_only=equities_only,
    )
    rows = _row_count(path)
    if path is None or rows <= 0:
        stats = {"rows": 0, "symbols": len(symbols), "uploaded": False, "skipped": False}
        print(f"[{date}] 没有可算的明细 耗时={_format_elapsed(time.perf_counter() - t0)}", flush=True)
        return {
            "date": date,
            "source": source,
            "stats": stats,
            "ok": False,
            "reason": "no_rows",
        }

    try:
        print(f"[{date}] 正在写入 D1 l2_factors", flush=True)
        factor_batch._upload_factor_file(path, None)
    except Exception:
        print(f"[{date}] 因子写入 D1 失败", flush=True)
        stats = {"rows": rows, "symbols": len(symbols), "uploaded": False, "skipped": False}
        return {
            "date": date,
            "source": source,
            "stats": stats,
            "ok": False,
            "reason": "upload_failed",
        }

    if not factor_batch._is_done(output_dir, date):
        factor_batch._mark_done(output_dir, date, rows=rows)
    factor_batch._mark_uploaded(output_dir, date)
    print(f"[{date}] 因子已写入 D1 rows={rows} 耗时={_format_elapsed(time.perf_counter() - t0)}", flush=True)

    stats = {"rows": rows, "symbols": len(symbols), "uploaded": True, "skipped": False}
    ok, reason = _can_delete_after_factors(stats)
    if delete and ok:
        removed = delete_sources(date, dry_run=False)
        if removed:
            print(f"[{date}] 已删除原始文件: {removed}", flush=True)
        else:
            print(f"[{date}] 未删除原始文件: 源路径不存在", flush=True)
    elif delete and not ok:
        print(f"[{date}] 未删除原始文件: {reason}", flush=True)
    return {
        "date": date,
        "source": source,
        "stats": stats,
        "ok": ok,
        "reason": reason,
    }


def convert_one_local(
    date: str,
    *,
    delete: bool,
    dry_run: bool,
    skip_existing: bool,
    equities_only: bool,
    workers: int | None,
) -> dict:
    """从已解压目录算因子并写 D1（阶段 A）。"""
    day_dir = config.DATA_ROOT / date
    if not day_dir.is_dir():
        raise FileNotFoundError(f"未找到已解压目录: {day_dir}")
    print(f"[{date}] 开始处理（local） {day_dir}", flush=True)
    return _process_day(
        date,
        source="local",
        delete=delete,
        dry_run=dry_run,
        skip_existing=skip_existing,
        equities_only=equities_only,
        workers=workers,
        force_extract=False,
    )


def convert_one_7z(
    date: str,
    *,
    delete: bool,
    dry_run: bool,
    skip_existing: bool,
    equities_only: bool,
    workers: int | None,
) -> dict:
    """整包解压当日 .7z 后算因子并写 D1（阶段 B 单日闭环）。"""
    seven_z = config.DATA_ROOT / f"{date}.7z"
    if not seven_z.exists():
        raise FileNotFoundError(seven_z)
    print(f"[{date}] 开始处理（7z） {seven_z}", flush=True)
    return _process_day(
        date,
        source="7z",
        delete=delete,
        dry_run=dry_run,
        skip_existing=skip_existing,
        equities_only=equities_only,
        workers=workers,
        # dry-run 不解压；已上传跳过时也不解压（在 _process_day 内提前 return）。
        force_extract=not dry_run,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            f"批量解压并算因子：扫描 {config.DATA_ROOT} 下全部 .7z/"
            "已解压目录，先 local 再逐日解压+CSV 算因子写 D1（严格串行，不落明细 Parquet）"
        )
    )
    parser.add_argument("--dates", nargs="*", help="仅处理这些交易日")
    parser.add_argument("--no-delete", action="store_true", help="写完不删 CSV/.7z")
    parser.add_argument("--local-only", action="store_true", help="仅处理已解压目录")
    parser.add_argument("--7z-only", action="store_true", help="仅处理 .7z（跳过 local 阶段）")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-skip", action="store_true", help="已写入 D1 的日期也重算并覆盖")
    parser.add_argument("--workers", type=int, default=None, help="因子计算并行度")
    parser.add_argument(
        "--all-symbols",
        action="store_true",
        help="默认不算可转债、B股等；加此参数才包含全部标的",
    )
    args = parser.parse_args(argv)

    delete = not args.no_delete
    skip_existing = not args.no_skip
    equities_only = not args.all_symbols
    dry_run = args.dry_run

    local_dates = [] if args.__dict__.get("7z_only") else _discover_local_dates(args.dates)
    all_7z = _discover_7z_dates(args.dates)
    # 未解压的日期：有 .7z 但无本地目录（阶段 B）
    local_set = set(local_dates)
    z7_dates = [] if args.__dict__.get("local_only") else [d for d in all_7z if d not in local_set]

    print(
        f"DATA_ROOT={config.DATA_ROOT} local={len(local_dates)} 7z={len(z7_dates)} "
        f"delete={delete} dry_run={dry_run} utc={datetime.now(timezone.utc).isoformat()}",
        flush=True,
    )
    if local_dates:
        print(f"  阶段A local 优先（写完才解压新包）: {local_dates}", flush=True)
    if z7_dates:
        print(f"  阶段B 7z 逐日串行: {z7_dates}", flush=True)
    if not local_dates and not z7_dates:
        print("无可处理日期，退出", flush=True)
        return 1

    summary: list[dict] = []
    t_all = time.perf_counter()

    # 阶段 A：已解压目录必须全部写完；未达标则不解压任何新 7z
    for date in local_dates:
        try:
            rec = convert_one_local(
                date,
                delete=delete,
                dry_run=dry_run,
                skip_existing=skip_existing,
                equities_only=equities_only,
                workers=args.workers,
            )
        except Exception:
            traceback.print_exc()
            print(f"[{date}] 异常退出，停止后续日期（不解压新 7z）", flush=True)
            break
        summary.append(rec)
        # dry_run 不解压，不据此中断后续日期
        if not dry_run and not rec["ok"]:
            print(f"当日未达标，停止。已处理: {[r['date'] for r in summary]}", flush=True)
            break
    else:
        # 阶段 B：逐日整包解压 → 算因子 → 写 D1 → 删源 → 再解下一包
        for date in z7_dates:
            try:
                rec = convert_one_7z(
                    date,
                    delete=delete,
                    dry_run=dry_run,
                    skip_existing=skip_existing,
                    equities_only=equities_only,
                    workers=args.workers,
                )
            except Exception:
                traceback.print_exc()
                print(f"[{date}] 异常退出，停止后续日期", flush=True)
                break
            summary.append(rec)
            if not dry_run and not rec["ok"]:
                print(f"当日未达标，停止。已处理: {[r['date'] for r in summary]}", flush=True)
                break

    print("==== 汇总 ====", flush=True)
    for rec in summary:
        s = rec["stats"]
        print(
            f"{rec['date']} ({rec['source']}) rows={s.get('rows', 0)} "
            f"symbols={s.get('symbols', 0)} uploaded={s.get('uploaded')} "
            f"skipped={s.get('skipped')} ok={rec['ok']}",
            flush=True,
        )
    print(f"总耗时: {_format_elapsed(time.perf_counter() - t_all)}", flush=True)
    print(f"因子目录: {factor_batch.default_output_dir()}", flush=True)

    planned = len(local_dates) + len(z7_dates)
    # dry_run 只验证调度是否跑完全部日期，不以删源门槛判定成功
    if dry_run:
        return 0 if len(summary) == planned else 1
    ok_all = len(summary) == planned and all(r["ok"] for r in summary)
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
