"""从 .staging/parquet 按日串行上传到当前 STORAGE_BACKEND。

日与日之间不并行；单日内可多线程。默认不删除本地 parquet。
百度物理路径由 baidu_path_from_key 自动加年/年月/日层级。
"""
from __future__ import annotations

import argparse
import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .symbols import is_default_symbol

from . import catalog, config, object_store
from .pipeline import _matches


def _format_elapsed(seconds: float) -> str:
    """秒数 → 可读耗时。"""
    total = max(0.0, seconds)
    if total >= 60:
        minutes = int(total // 60)
        secs = int(total % 60)
        return f"{minutes}分{secs}秒（{total:.1f}s）"
    return f"{total:.1f}s"


def _discover_staging_dates(only: list[str] | None = None) -> list[str]:
    """扫描 STAGING_PARQUET 下 8 位日期目录。"""
    root = config.STAGING_PARQUET
    if not root.is_dir():
        return []
    dates = sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and p.name.isdigit() and len(p.name) == 8
    )
    if only:
        wanted = set(only)
        missing = wanted - set(dates)
        if missing:
            raise FileNotFoundError(f"staging 中找不到日期目录: {sorted(missing)}")
        dates = [d for d in dates if d in wanted]
    return dates


def _print_progress(done: int, total: int, stats: dict[str, int]) -> None:
    if done == total or done % 100 == 0:
        print(
            f"  进度 {done}/{total} uploaded={stats['uploaded']} "
            f"skipped={stats['skipped']} failed={stats['failed']}",
            flush=True,
        )


def _periodic_flush(date: str, uploaded: int) -> None:
    if uploaded > 0 and uploaded % 60 == 0:
        catalog.flush_catalog(date)


def _log_failure(date: str, label: str, exc: Exception) -> None:
    config.FAILURE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.FAILURE_DIR / f"upload_{date}.jsonl"
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "member": label, "error": str(exc)}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _upload_one(date: str, code: str, ftype: str, pq_path: Path) -> dict[str, Any]:
    """读本地 parquet 字节并 PUT。"""
    data = pq_path.read_bytes()
    key = config.object_key(date, code, ftype)
    etag = object_store.upload_bytes(key, data)
    return {
        "date": date,
        "code": code,
        "ftype": ftype,
        "nbytes": len(data),
        "etag": etag,
        "fail_label": f"{date}/{code}/{ftype}",
    }


def upload_staging_date(
    date: str,
    *,
    codes: set[str] | None = None,
    ftypes: set[str] | None = None,
    dry_run: bool = False,
    skip_existing: bool = True,
    equities_only: bool = True,
    workers: int | None = None,
) -> dict[str, int]:
    """上传单个交易日的 staging parquet。"""
    day_dir = config.STAGING_PARQUET / date
    if not day_dir.is_dir():
        raise FileNotFoundError(f"未找到 staging 目录: {day_dir}")

    stats = {"total": 0, "uploaded": 0, "skipped": 0, "failed": 0, "filtered_non_equity": 0}
    uploaded_keys: set[str] = set()
    if skip_existing:
        uploaded_keys = catalog.get_uploaded_keys(date)
        if not uploaded_keys and object_store.is_configured():
            try:
                uploaded_keys = catalog.sync_from_remote_prefix(date)
            except Exception as exc:
                print(f"[WARN] 远程前缀列举失败，跳过存在检查: {exc}", flush=True)

    candidates: list[tuple[str, str, Path]] = []
    for code_dir in sorted(day_dir.iterdir()):
        if not code_dir.is_dir():
            continue
        code = code_dir.name
        if equities_only and not is_default_symbol(code):
            for ftype in config.FILE_TYPES:
                if ftypes and ftype not in ftypes:
                    continue
                if codes and code not in codes and code.split(".")[0] not in codes:
                    continue
                if (code_dir / f"{ftype}.parquet").exists():
                    stats["filtered_non_equity"] += 1
            continue
        for ftype in config.FILE_TYPES:
            if not _matches(code, ftype, codes, ftypes, equities_only=False):
                continue
            pq_path = code_dir / f"{ftype}.parquet"
            if pq_path.is_file():
                candidates.append((code, ftype, pq_path))

    total_candidates = len(candidates)
    print(f"  待处理 {total_candidates} 个文件（staging）", flush=True)

    n_workers = max(1, workers if workers is not None else config.ingest_workers())
    to_upload: list[tuple[str, str, Path]] = []
    done = 0
    for code, ftype, pq_path in candidates:
        stats["total"] += 1
        key = config.object_key(date, code, ftype)
        if skip_existing and key in uploaded_keys:
            stats["skipped"] += 1
            done += 1
            _print_progress(done, total_candidates, stats)
            continue
        if dry_run:
            done += 1
            _print_progress(done, total_candidates, stats)
            continue
        to_upload.append((code, ftype, pq_path))

    if not to_upload:
        catalog.flush_catalog(date)
        if stats["uploaded"] > 0:
            catalog.upload_catalog(date)
        return stats

    object_store.configure_pool(n_workers + 8)
    print(
        f"  待上传 {len(to_upload)} 个文件（backend={object_store.backend()} workers={n_workers}）",
        flush=True,
    )
    # 示例路径确认百度层级映射
    sample_key = config.object_key(date, to_upload[0][0], to_upload[0][1])
    if object_store.backend() == "baidu":
        print(f"  示例百度路径: {config.baidu_path_from_key(sample_key)}", flush=True)

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures_map = {
            pool.submit(_upload_one, date, code, ftype, pq_path): f"{date}/{code}/{ftype}"
            for code, ftype, pq_path in to_upload
        }
        for fut in as_completed(futures_map):
            fail_label = futures_map[fut]
            try:
                rec = fut.result()
                catalog.record_upload(
                    rec["date"],
                    rec["code"],
                    rec["ftype"],
                    rows=0,
                    nbytes=rec["nbytes"],
                    etag=rec["etag"],
                )
                stats["uploaded"] += 1
                _periodic_flush(date, stats["uploaded"])
            except Exception as exc:
                stats["failed"] += 1
                _log_failure(date, fail_label, exc)
                print(f"[FAIL] {fail_label}: {exc}", flush=True)
            done += 1
            _print_progress(done, total_candidates, stats)

    catalog.flush_catalog(date)
    if stats["uploaded"] > 0:
        catalog.upload_catalog(date)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=f"从 {config.STAGING_PARQUET} 按日串行上传到当前 STORAGE_BACKEND"
    )
    parser.add_argument("--dates", nargs="*", help="仅上传这些交易日")
    parser.add_argument("--code", action="append")
    parser.add_argument("--type", action="append", dest="ftypes", choices=config.FILE_TYPES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-skip", action="store_true")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument(
        "--all-symbols",
        action="store_true",
        help="默认不上传可转债、B股等；加此参数才包含全部标的",
    )
    args = parser.parse_args(argv)

    if not object_store.is_configured():
        print(f"存储后端 {object_store.backend()} 未配置，中止", flush=True)
        return 2

    codes = set(args.code) if args.code else None
    ftypes = set(args.ftypes) if args.ftypes else None
    skip_existing = not args.no_skip
    equities_only = not args.all_symbols

    dates = _discover_staging_dates(args.dates)
    print(
        f"STAGING={config.STAGING_PARQUET} backend={object_store.backend()} "
        f"dates={len(dates)} dry_run={args.dry_run} "
        f"utc={datetime.now(timezone.utc).isoformat()}",
        flush=True,
    )
    if not dates:
        print("无可上传日期，退出", flush=True)
        return 1
    print(f"  按日串行: {dates}", flush=True)

    summary: list[dict] = []
    t_all = time.perf_counter()
    for date in dates:
        print(f"[{date}] 开始上传 staging", flush=True)
        t0 = time.perf_counter()
        try:
            stats = upload_staging_date(
                date,
                codes=codes,
                ftypes=ftypes,
                dry_run=args.dry_run,
                skip_existing=skip_existing,
                equities_only=equities_only,
                workers=args.workers,
            )
        except Exception:
            traceback.print_exc()
            print(f"[{date}] 异常，继续下一交易日", flush=True)
            summary.append({
                "date": date,
                "stats": {"total": 0, "uploaded": 0, "skipped": 0, "failed": 1},
                "ok": False,
            })
            continue
        ok = stats["failed"] == 0
        print(
            f"[{date}] 完成: {stats} 耗时={_format_elapsed(time.perf_counter() - t0)} ok={ok}",
            flush=True,
        )
        if stats.get("filtered_non_equity"):
            print(f"[{date}] 已过滤非默认标的: {stats['filtered_non_equity']}", flush=True)
        summary.append({"date": date, "stats": stats, "ok": ok})

    print("==== 汇总 ====", flush=True)
    for rec in summary:
        s = rec["stats"]
        print(
            f"{rec['date']} total={s['total']} uploaded={s['uploaded']} "
            f"skipped={s['skipped']} failed={s['failed']} ok={rec['ok']}",
            flush=True,
        )
    print(f"总耗时: {_format_elapsed(time.perf_counter() - t_all)}", flush=True)

    if args.dry_run:
        return 0 if len(summary) == len(dates) else 1
    ok_all = len(summary) == len(dates) and all(r["ok"] for r in summary)
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
