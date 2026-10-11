"""CLI：python -m app.services.level2_factors.l2_daily"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app.services.level2_factors.book import default_parquet_directory
from app.services.level2_ingest import config as ingest_config

from .catalog import ALL_GROUPS, FACTOR_VERSION
from .orchestrator import run


def _parse_dates(args: argparse.Namespace) -> list[str]:
    if args.dates:
        return [item.strip() for item in args.dates.split(",") if item.strip()]
    if args.start and args.end:
        start = str(args.start)
        end = str(args.end)
        if not (start.isdigit() and end.isdigit() and len(start) == 8 and len(end) == 8):
            raise SystemExit("--start/--end 需要 YYYYMMDD")
        # 从 parquet 根列举区间内已有日期
        root = _parquet_root(args)
        dates = []
        if root.is_dir():
            for child in sorted(root.iterdir()):
                name = child.name
                if child.is_dir() and name.isdigit() and len(name) == 8 and start <= name <= end:
                    dates.append(name)
        return dates
    raise SystemExit("需要 --dates 或 --start/--end")


def _parquet_root(args: argparse.Namespace) -> Path:
    if args.parquet_dir:
        return Path(args.parquet_dir)
    env = os.getenv("LEVEL2_PARQUET_DIR", "").strip()
    if env:
        return Path(env)
    staging = ingest_config.STAGING_PARQUET
    if staging.is_dir():
        return staging
    return default_parquet_directory()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="L2 百因子日频计算（并行新链路）")
    parser.add_argument("--dates", default="", help="逗号分隔交易日 YYYYMMDD")
    parser.add_argument("--start", default="", help="起始交易日 YYYYMMDD")
    parser.add_argument("--end", default="", help="结束交易日 YYYYMMDD")
    parser.add_argument("--parquet-dir", default="", help="明细 Parquet 根目录")
    parser.add_argument("--output", default="", help="因子输出根，默认 LEVEL2_L2_DAILY_ROOT")
    parser.add_argument(
        "--groups",
        default="",
        help=f"逗号分隔组名，默认全部：{','.join(ALL_GROUPS)}",
    )
    parser.add_argument("--force", action="store_true", help="忽略完成标记重算")
    parser.add_argument("--no-r2", action="store_true", help="不上传 R2")
    parser.add_argument("--no-compact", action="store_true", help="不跑月 compact")
    parser.add_argument("--no-seed", action="store_true", help="不写 D1 因子定义种子")
    parser.add_argument("--factor-version", type=int, default=FACTOR_VERSION)
    args = parser.parse_args(argv)

    dates = _parse_dates(args)
    groups = [g.strip() for g in args.groups.split(",") if g.strip()] or None
    if groups:
        unknown = set(groups) - set(ALL_GROUPS)
        if unknown:
            raise SystemExit(f"未知 factor_group: {sorted(unknown)}")

    parquet_root = _parquet_root(args)
    output = Path(args.output) if args.output else None
    print(
        f"l2_daily dates={len(dates)} groups={groups or list(ALL_GROUPS)} "
        f"parquet={parquet_root} force={args.force}",
        flush=True,
    )
    summary = run(
        dates,
        parquet_root=parquet_root,
        output_root=output,
        groups=groups,
        force=args.force,
        factor_version=args.factor_version,
        upload_r2=not args.no_r2,
        seed_defs=not args.no_seed,
        compact_months=not args.no_compact,
    )
    print(summary, flush=True)
    return 1 if int(summary.get("failed") or 0) > 0 and int(summary.get("processed") or 0) == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
