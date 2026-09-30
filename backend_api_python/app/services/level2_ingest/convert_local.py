"""7z 整包解压 / 本地 CSV 转 Parquet 落盘（不上传云端）。

多日场景由上层串行调度：转完（并删源）再解下一包。
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .symbols import is_default_symbol

from . import build_manifest, config, csv_to_parquet, extract
from .pipeline import _matches

# 与 ingest_all / sync_catalog 一致：低于此视为异常，禁止删源文件
_MIN_EQUITY_FILES = 10_000


def _format_elapsed(seconds: float) -> str:
    """将秒数格式化为可读耗时：满 1 分钟为「X分Y秒（Ns）」，否则仅「Ns」。"""
    total = max(0.0, seconds)
    if total >= 60:
        minutes = int(total // 60)
        secs = int(total % 60)
        return f"{minutes}分{secs}秒（{total:.1f}s）"
    return f"{total:.1f}s"


def _can_delete_sources(stats: dict[str, int]) -> tuple[bool, str]:
    """转换 stats 是否达标，可安全删除 CSV 目录与 .7z。"""
    failed = int(stats.get("failed", 0))
    total = int(stats.get("total", 0))
    converted = int(stats.get("converted", 0))
    skipped = int(stats.get("skipped", 0))
    if failed != 0:
        return False, f"failed={failed}"
    if converted + skipped != total:
        return False, f"converted+skipped={converted + skipped} != total={total}"
    if total < _MIN_EQUITY_FILES:
        return False, f"total={total} < {_MIN_EQUITY_FILES}"
    return True, "ok"


def delete_sources(date: str, *, dry_run: bool = False) -> list[str]:
    """删除 202608/{date}/ 与 {date}.7z，返回路径列表；dry_run 时不实际删除。"""
    deleted: list[str] = []
    day_dir = config.DATA_ROOT / date
    seven_z = config.DATA_ROOT / f"{date}.7z"
    if day_dir.is_dir():
        if not dry_run:
            shutil.rmtree(day_dir)
        deleted.append(str(day_dir))
    if seven_z.is_file():
        if not dry_run:
            seven_z.unlink()
        deleted.append(str(seven_z))
    return deleted


def maybe_delete_sources(
    date: str,
    stats: dict[str, int],
    *,
    enabled: bool,
    dry_run: bool,
) -> None:
    """转换正常结束后，达标则删除原始 CSV 目录与 .7z。"""
    if not enabled:
        return
    if dry_run:
        return
    ok, reason = _can_delete_sources(stats)
    if not ok:
        print(f"未删除原始文件: {reason}")
        return
    removed = delete_sources(date, dry_run=False)
    if removed:
        print(f"已删除原始文件: {removed}")
    else:
        print("未删除原始文件: 源路径不存在")


def _print_progress(done: int, total: int, stats: dict[str, int]) -> None:
    """每 100 个候选文件打印一次进度。"""
    if done == total or done % 100 == 0:
        print(
            f"  进度 {done}/{total} converted={stats['converted']} "
            f"skipped={stats['skipped']} failed={stats['failed']}",
            flush=True,
        )


def _log_failure(date: str, label: str, exc: Exception) -> None:
    config.FAILURE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.FAILURE_DIR / f"{date}.jsonl"
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "member": label, "error": str(exc)}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _convert_local_one(date: str, code: str, ftype: str, csv_path: Path) -> dict[str, Any]:
    """工作线程：本地 CSV → Parquet。"""
    out = config.local_parquet_path(date, code, ftype)
    csv_to_parquet.csv_file_to_parquet(csv_path, out, ftype)
    return {
        "fail_label": f"{date}/{code}/{ftype}",
        "nbytes": out.stat().st_size,
        "path": str(out),
    }


def _drain_conversions(
    date: str,
    futures_map: dict,
    stats: dict[str, int],
    done: int,
    total_candidates: int,
) -> int:
    """主线程收集转换结果，写失败日志与进度。"""
    for fut in as_completed(futures_map):
        fail_label = futures_map[fut]
        try:
            fut.result()
            stats["converted"] += 1
        except Exception as exc:
            stats["failed"] += 1
            _log_failure(date, fail_label, exc)
            print(f"[FAIL] {fail_label}: {exc}", flush=True)
        done += 1
        _print_progress(done, total_candidates, stats)
    return done


def convert_7z(
    seven_z_path: str | Path,
    codes: set[str] | None = None,
    ftypes: set[str] | None = None,
    dry_run: bool = False,
    skip_existing: bool = True,
    equities_only: bool = True,
    workers: int | None = None,
) -> dict[str, int]:
    """整包解压 .7z 到本地后，走 convert_local_date 转 Parquet。

    dry_run 时不解压，仅在已有日目录上预估；无目录则返回空 stats。
    """
    seven_z_path = Path(seven_z_path)
    date = seven_z_path.stem
    if not dry_run:
        extract.extract_archive(seven_z_path)
    day_dir = config.DATA_ROOT / date
    if not day_dir.is_dir():
        if dry_run:
            print(f"  dry-run：无本地目录 {day_dir}，跳过（不解压）", flush=True)
            return {
                "total": 0,
                "converted": 0,
                "skipped": 0,
                "failed": 0,
                "filtered_non_equity": 0,
            }
        raise FileNotFoundError(f"解压后未找到日目录: {day_dir}")
    return convert_local_date(
        date,
        codes=codes,
        ftypes=ftypes,
        dry_run=dry_run,
        skip_existing=skip_existing,
        equities_only=equities_only,
        workers=workers,
    )


def convert_local_date(
    date: str,
    codes: set[str] | None = None,
    ftypes: set[str] | None = None,
    dry_run: bool = False,
    skip_existing: bool = True,
    equities_only: bool = True,
    workers: int | None = None,
) -> dict[str, int]:
    """从已解压目录 202608/{date}/ 转换 Parquet。"""
    day_dir = config.DATA_ROOT / date
    if not day_dir.exists():
        raise FileNotFoundError(f"未找到已解压目录: {day_dir}")

    stats = {"total": 0, "converted": 0, "skipped": 0, "failed": 0, "filtered_non_equity": 0}
    candidates: list[tuple[str, str, Path]] = []
    for code_dir in sorted(day_dir.iterdir()):
        if not code_dir.is_dir():
            continue
        code = code_dir.name
        # 默认保留 A 股 + 场内基金；可转债/B股等计入 filtered
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

    n_workers = max(1, workers if workers is not None else config.INGEST_WORKERS)
    to_convert: list[tuple[str, str, Path]] = []
    done = 0
    for code, ftype, csv_path in candidates:
        stats["total"] += 1
        pq_path = config.local_parquet_path(date, code, ftype)
        if skip_existing and pq_path.exists():
            stats["skipped"] += 1
            done += 1
            _print_progress(done, total_candidates, stats)
            continue
        if dry_run:
            done += 1
            _print_progress(done, total_candidates, stats)
            continue
        to_convert.append((code, ftype, csv_path))

    if not to_convert:
        return stats

    print(f"  待转换 {len(to_convert)} 个文件（local，workers={n_workers}）", flush=True)
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures_map = {
            pool.submit(_convert_local_one, date, code, ftype, csv_path): f"{date}/{code}/{ftype}"
            for code, ftype, csv_path in to_convert
        }
        _drain_conversions(date, futures_map, stats, done, total_candidates)
    return stats


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="7z 整包解压 / 本地 CSV 转 Parquet（不上传）；单日闭环"
    )
    parser.add_argument("--date", required=True, help="交易日，对应 202608/{date}.7z")
    parser.add_argument("--code", action="append")
    parser.add_argument("--type", action="append", dest="ftypes", choices=config.FILE_TYPES)
    parser.add_argument("--source", choices=("auto", "7z", "local"), default="7z")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-skip", action="store_true")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument(
        "--all-symbols",
        action="store_true",
        help="默认不转换可转债、B股等；加此参数才包含全部标的",
    )
    parser.add_argument(
        "--no-delete",
        action="store_true",
        help="转换完成后不删除 CSV 目录与 .7z（默认会删）",
    )
    args = parser.parse_args(argv)

    codes = set(args.code) if args.code else None
    ftypes = set(args.ftypes) if args.ftypes else None
    skip_existing = not args.no_skip
    equities_only = not args.all_symbols

    seven_z = config.DATA_ROOT / f"{args.date}.7z"
    day_dir = config.DATA_ROOT / args.date
    source = args.source
    # auto：有已解压目录则优先 local，再解压下一包前先转完已落地数据
    if source == "auto":
        source = "local" if day_dir.is_dir() else ("7z" if seven_z.exists() else "local")

    # 计时覆盖整包解压（若有）+ 转换本身，不含事后删源
    t0 = time.perf_counter()
    if source == "7z":
        if not seven_z.exists():
            raise FileNotFoundError(seven_z)
        # 可选：保留 manifest 供其它工具使用（转换本身不再依赖）
        if not args.dry_run and not config.local_manifest_path(args.date).exists():
            print(f"[{args.date}] 生成 manifest（仅此一次 tar -tf）")
            build_manifest.build(args.date)
        stats = convert_7z(
            seven_z,
            codes=codes,
            ftypes=ftypes,
            dry_run=args.dry_run,
            skip_existing=skip_existing,
            equities_only=equities_only,
            workers=args.workers,
        )
    else:
        stats = convert_local_date(
            args.date,
            codes=codes,
            ftypes=ftypes,
            dry_run=args.dry_run,
            skip_existing=skip_existing,
            equities_only=equities_only,
            workers=args.workers,
        )
    elapsed = time.perf_counter() - t0

    if stats.get("filtered_non_equity"):
        print(f"已过滤非默认标的文件: {stats['filtered_non_equity']}（可转债/B股等）")
    print(f"输出目录: {config.STAGING_PARQUET}")
    print(f"处理完成: {stats}")
    print(f"耗时: {_format_elapsed(elapsed)}")
    maybe_delete_sources(
        args.date,
        stats,
        enabled=not args.no_delete,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
