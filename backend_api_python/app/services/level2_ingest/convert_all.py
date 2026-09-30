"""按日全量本地转 Parquet：多日严格串行（不上传云端）。

阶段 A：先处理所有已解压 local 目录；未达标则停止，不解压任何新 7z。
阶段 B：对剩余 .7z 逐日「整包解压到 DATA_ROOT → 转换 → 达标删 CSV+.7z → 再解下一包」。
解压落点为 config.DATA_ROOT（默认 202608/{date}/）。
"""
from __future__ import annotations

import argparse
import time
import traceback
from datetime import datetime, timezone

from . import build_manifest, config
from .convert_local import (
    _can_delete_sources,
    _format_elapsed,
    convert_7z,
    convert_local_date,
    maybe_delete_sources,
)


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


def convert_one_local(
    date: str,
    *,
    delete: bool,
    dry_run: bool,
    skip_existing: bool,
    equities_only: bool,
    workers: int | None,
) -> dict:
    """从已解压目录转换（阶段 A）。"""
    day_dir = config.DATA_ROOT / date
    if not day_dir.is_dir():
        raise FileNotFoundError(f"未找到已解压目录: {day_dir}")

    print(f"[{date}] 开始转换（local） {day_dir}", flush=True)
    t0 = time.perf_counter()
    stats = convert_local_date(
        date,
        dry_run=dry_run,
        skip_existing=skip_existing,
        equities_only=equities_only,
        workers=workers,
    )
    print(f"[{date}] 完成: {stats} 耗时={_format_elapsed(time.perf_counter() - t0)}", flush=True)
    maybe_delete_sources(date, stats, enabled=delete, dry_run=dry_run)
    ok, reason = _can_delete_sources(stats)
    return {
        "date": date,
        "source": "local",
        "stats": stats,
        "ok": ok,
        "reason": reason,
    }


def convert_one_7z(
    date: str,
    *,
    delete: bool,
    dry_run: bool,
    skip_existing: bool,
    equities_only: bool,
    workers: int | None,
) -> dict:
    """整包解压当日 .7z 到 DATA_ROOT 后转换（阶段 B 单日闭环）。"""
    seven_z = config.DATA_ROOT / f"{date}.7z"
    if not seven_z.exists():
        raise FileNotFoundError(seven_z)

    if not dry_run and not config.local_manifest_path(date).exists():
        print(f"[{date}] 生成 manifest（仅此一次 tar -tf）", flush=True)
        build_manifest.build(date)

    print(f"[{date}] 开始转换（7z 整包解压 → {config.DATA_ROOT}） {seven_z}", flush=True)
    t0 = time.perf_counter()
    stats = convert_7z(
        seven_z,
        dry_run=dry_run,
        skip_existing=skip_existing,
        equities_only=equities_only,
        workers=workers,
    )
    print(f"[{date}] 完成: {stats} 耗时={_format_elapsed(time.perf_counter() - t0)}", flush=True)
    maybe_delete_sources(date, stats, enabled=delete, dry_run=dry_run)
    ok, reason = _can_delete_sources(stats)
    return {
        "date": date,
        "source": "7z",
        "stats": stats,
        "ok": ok,
        "reason": reason,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            f"批量转 Parquet：扫描 {config.DATA_ROOT} 下全部 .7z/"
            "已解压目录，先 local 再逐日解压+转换（严格串行）"
        )
    )
    parser.add_argument("--dates", nargs="*", help="仅处理这些交易日")
    parser.add_argument("--no-delete", action="store_true", help="转完不删 CSV/.7z")
    parser.add_argument("--local-only", action="store_true", help="仅处理已解压目录")
    parser.add_argument("--7z-only", action="store_true", help="仅处理 .7z（跳过 local 阶段）")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-skip", action="store_true")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument(
        "--all-symbols",
        action="store_true",
        help="默认不转换可转债、B股等；加此参数才包含全部标的",
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
        print(f"  阶段A local 优先（转完才解压新包）: {local_dates}", flush=True)
    if z7_dates:
        print(f"  阶段B 7z 逐日串行: {z7_dates}", flush=True)
    if not local_dates and not z7_dates:
        print("无可处理日期，退出", flush=True)
        return 1

    summary: list[dict] = []
    t_all = time.perf_counter()

    # 阶段 A：已解压目录必须全部转完；未达标则不解压任何新 7z
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
        # dry_run 不解压，stats 可能为空，不据此中断后续日期
        if not dry_run and not rec["ok"]:
            print(f"当日未达标，停止。已处理: {[r['date'] for r in summary]}", flush=True)
            break
    else:
        # 阶段 B：逐日整包解压 → 转换 → 删源 → 再解下一包
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
            f"{rec['date']} ({rec['source']}) total={s['total']} converted={s['converted']} "
            f"skipped={s['skipped']} failed={s['failed']} ok={rec['ok']}",
            flush=True,
        )
    print(f"总耗时: {_format_elapsed(time.perf_counter() - t_all)}", flush=True)
    print(f"输出目录: {config.STAGING_PARQUET}", flush=True)
    print("因子请另跑: ./scripts/run_level2_factors.sh all", flush=True)

    planned = len(local_dates) + len(z7_dates)
    # dry_run 只验证调度是否跑完全部日期，不以删源门槛判定成功
    if dry_run:
        return 0 if len(summary) == planned else 1
    ok_all = len(summary) == planned and all(r["ok"] for r in summary)
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
