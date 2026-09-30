"""编排：整包解压或本地 CSV → Parquet → 云存储，catalog 幂等跳过。

多日由 ingest_all 串行：先转完已解压目录，再「解压一日 → 入库完 → 删源 → 下一包」。
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .symbols import is_default_symbol

from . import catalog, config, csv_to_parquet, extract, manifest, object_store


def _matches(
    code: str,
    ftype: str,
    codes: set[str] | None,
    ftypes: set[str] | None,
    equities_only: bool,
) -> bool:
    # equities_only：默认保留 A 股 + 场内基金，排除可转债/B股等
    if equities_only and not is_default_symbol(code):
        return False
    if codes and code not in codes and code.split(".")[0] not in codes:
        return False
    if ftypes and ftype not in ftypes:
        return False
    return True


def _print_progress(done: int, total: int, stats: dict[str, int]) -> None:
    """每 100 个候选文件打印一次，避免长时间无日志被误判为卡住。"""
    if done == total or done % 100 == 0:
        print(
            f"  进度 {done}/{total} uploaded={stats['uploaded']} "
            f"skipped={stats['skipped']} failed={stats['failed']}",
            flush=True,
        )


def _periodic_flush(date: str, uploaded: int) -> None:
    """每满 60 次上传落盘 catalog，中断后可凭 skip_existing 续传。"""
    if uploaded > 0 and uploaded % 60 == 0:
        catalog.flush_catalog(date)


def _log_failure(date: str, member: str, exc: Exception) -> None:
    config.FAILURE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.FAILURE_DIR / f"{date}.jsonl"
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "member": member, "error": str(exc)}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _upload_local_one(date: str, code: str, ftype: str, csv_path: Path) -> dict[str, Any]:
    """工作线程：读 CSV → Parquet → PUT。返回供主线程写 catalog 的结果。"""
    key = config.object_key(date, code, ftype)
    pq_bytes = csv_to_parquet.csv_bytes_to_parquet_bytes(csv_path.read_bytes(), ftype)
    etag = object_store.upload_bytes(key, pq_bytes)
    return {
        "date": date,
        "code": code,
        "ftype": ftype,
        "nbytes": len(pq_bytes),
        "etag": etag,
        "fail_label": f"{date}/{code}/{ftype}",
    }


def _drain_uploads(
    date: str,
    futures_map: dict,
    stats: dict[str, int],
    done: int,
    total_candidates: int,
) -> int:
    """主线程收集线程池结果：写 catalog、失败日志、进度（避免 catalog 竞态）。"""
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
    return done


def _process_7z_dry_run_via_manifest(
    seven_z_path: Path,
    codes: set[str] | None,
    ftypes: set[str] | None,
    skip_existing: bool,
    equities_only: bool,
) -> dict[str, int]:
    """dry-run 不解压：用 manifest 统计过滤与待上传规模（供测试/预估）。"""
    date = seven_z_path.stem
    stats = {"total": 0, "uploaded": 0, "skipped": 0, "failed": 0, "filtered_non_equity": 0}
    members = manifest.load_manifest(date, seven_z_path)
    if equities_only:
        stats["filtered_non_equity"] = sum(1 for m in members if not is_default_symbol(m.code))

    uploaded_keys: set[str] = set()
    if skip_existing:
        uploaded_keys = catalog.get_uploaded_keys(date)

    matched = [m for m in members if _matches(m.code, m.ftype, codes, ftypes, equities_only)]
    total_candidates = len(matched)
    done = 0
    for m in matched:
        stats["total"] += 1
        key = config.object_key(m.date, m.code, m.ftype)
        if skip_existing and key in uploaded_keys:
            stats["skipped"] += 1
        done += 1
        _print_progress(done, total_candidates, stats)
    return stats


def process_7z(
    seven_z_path: str | Path,
    codes: set[str] | None = None,
    ftypes: set[str] | None = None,
    dry_run: bool = False,
    skip_existing: bool = True,
    equities_only: bool = True,
    workers: int | None = None,
) -> dict[str, int]:
    """整包解压 .7z 后走 process_local_date 入库。

    dry_run 时不解压，改用 manifest 统计。
    """
    seven_z_path = Path(seven_z_path)
    date = seven_z_path.stem
    if dry_run:
        return _process_7z_dry_run_via_manifest(
            seven_z_path, codes, ftypes, skip_existing, equities_only
        )
    extract.extract_archive(seven_z_path)
    return process_local_date(
        date,
        codes=codes,
        ftypes=ftypes,
        dry_run=False,
        skip_existing=skip_existing,
        equities_only=equities_only,
        workers=workers,
    )


def process_local_date(
    date: str,
    codes: set[str] | None = None,
    ftypes: set[str] | None = None,
    dry_run: bool = False,
    skip_existing: bool = True,
    equities_only: bool = True,
    workers: int | None = None,
) -> dict[str, int]:
    day_dir = config.DATA_ROOT / date
    if not day_dir.exists():
        raise FileNotFoundError(f"未找到已解压目录: {day_dir}")

    stats = {"total": 0, "uploaded": 0, "skipped": 0, "failed": 0, "filtered_non_equity": 0}
    uploaded_keys: set[str] = set()
    if skip_existing:
        uploaded_keys = catalog.get_uploaded_keys(date)
        if not uploaded_keys and object_store.is_configured():
            try:
                uploaded_keys = catalog.sync_from_remote_prefix(date)
            except Exception as exc:
                print(f"[WARN] 远程前缀列举失败，跳过存在检查: {exc}", flush=True)

    # 先数候选文件，进度分母才稳定
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
                if config.local_csv_path(date, code, ftype).exists():
                    stats["filtered_non_equity"] += 1
            continue
        for ftype in config.FILE_TYPES:
            if not _matches(code, ftype, codes, ftypes, equities_only=False):
                continue
            csv_path = config.local_csv_path(date, code, ftype)
            if csv_path.exists():
                candidates.append((code, ftype, csv_path))

    total_candidates = len(candidates)
    print(f"  待处理 {total_candidates} 个文件（local）", flush=True)

    n_workers = max(1, workers if workers is not None else config.ingest_workers())
    to_upload: list[tuple[str, str, Path]] = []
    done = 0
    for code, ftype, csv_path in candidates:
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
        to_upload.append((code, ftype, csv_path))

    if not to_upload:
        catalog.flush_catalog(date)
        if stats["uploaded"] > 0:
            catalog.upload_catalog(date)
        return stats

    object_store.configure_pool(n_workers + 8)
    print(
        f"  待上传 {len(to_upload)} 个文件（local，backend={object_store.backend()} workers={n_workers}）",
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures_map = {
            pool.submit(_upload_local_one, date, code, ftype, csv_path): f"{date}/{code}/{ftype}"
            for code, ftype, csv_path in to_upload
        }
        done = _drain_uploads(date, futures_map, stats, done, total_candidates)

    catalog.flush_catalog(date)
    if stats["uploaded"] > 0:
        catalog.upload_catalog(date)
    return stats


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Level-2 CSV → Parquet → 云存储管道")
    parser.add_argument("--date", required=True)
    parser.add_argument("--code", action="append")
    parser.add_argument("--type", action="append", dest="ftypes", choices=config.FILE_TYPES)
    parser.add_argument("--source", choices=("auto", "7z", "local"), default="auto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-skip", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="并发上传线程数；默认 INGEST_WORKERS（7z 整包解压后亦走 local 并发）",
    )
    parser.add_argument(
        "--all-symbols",
        action="store_true",
        help="默认不上传可转债、B股等；加此参数才包含全部标的（含可转债/B股）",
    )
    args = parser.parse_args(argv)

    codes = set(args.code) if args.code else None
    ftypes = set(args.ftypes) if args.ftypes else None
    skip_existing = not args.no_skip
    equities_only = not args.all_symbols

    seven_z = config.DATA_ROOT / f"{args.date}.7z"
    day_dir = config.DATA_ROOT / args.date
    source = args.source
    # auto：已有日目录优先 local；否则有 .7z 则整包解压后入库
    if source == "auto":
        source = "local" if day_dir.is_dir() else ("7z" if seven_z.exists() else "local")

    if source == "7z":
        if not seven_z.exists():
            raise FileNotFoundError(seven_z)
        stats = process_7z(
            seven_z,
            codes=codes,
            ftypes=ftypes,
            dry_run=args.dry_run,
            skip_existing=skip_existing,
            equities_only=equities_only,
            workers=args.workers,
        )
    else:
        stats = process_local_date(
            args.date,
            codes=codes,
            ftypes=ftypes,
            dry_run=args.dry_run,
            skip_existing=skip_existing,
            equities_only=equities_only,
            workers=args.workers,
        )

    if stats.get("filtered_non_equity"):
        print(f"已过滤非默认标的文件: {stats['filtered_non_equity']}（可转债/B股等，未上传）")
    print(f"处理完成: {stats}")


if __name__ == "__main__":
    main()
