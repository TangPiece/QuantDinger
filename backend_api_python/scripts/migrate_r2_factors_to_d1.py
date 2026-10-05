#!/usr/bin/env python3
"""把 R2 / 本地日宽表因子批量迁到 D1。

默认 ``--mode wrangler``：生成字面量多行 INSERT 的 SQL 分片，供
``npx wrangler d1 execute <DB> --remote --file=...`` 导入，尽量减少写入次数。
``--mode worker``：同样用字面量 SQL，经 Worker ``/v1/batch`` 提交。

不迁移 ``l2_factors/symbol/`` 镜像。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 保证以脚本方式运行时能 import app。
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="迁移 Level2 日因子到 D1")
    parser.add_argument("--date", default="", help="只迁移这一天 YYYYMMDD")
    parser.add_argument("--start", default="", help="起始交易日（含）")
    parser.add_argument("--end", default="", help="结束交易日（含）")
    parser.add_argument(
        "--mode",
        choices=("wrangler", "worker"),
        default="wrangler",
        help="wrangler=生成 SQL 文件；worker=经 Worker 写入",
    )
    parser.add_argument(
        "--out-dir",
        default="",
        help="SQL 分片输出目录，默认 data/level2_d1_migrate",
    )
    parser.add_argument(
        "--local-dir",
        default="",
        help="优先读取的本地日 parquet 目录；也可只迁本地不连 R2",
    )
    parser.add_argument("--force", action="store_true", help="忽略已迁移标记")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写文件/不写 D1")
    parser.add_argument("--local-only", action="store_true", help="不列举/下载 R2，只扫本地")
    args = parser.parse_args(argv)

    from app.services.level2_factor_panel import default_factor_directory, panel_directory
    from app.services.level2_factors import d1_client, d1_factors
    from app.services.level2_factors.r2_factors import download_factor_file, list_factor_dates

    out_dir = Path(args.out_dir) if args.out_dir else _ROOT / "data" / "level2_d1_migrate"
    local_dirs = []
    if args.local_dir:
        local_dirs.append(Path(args.local_dir))
    local_dirs.extend([panel_directory(), default_factor_directory()])
    staging = _ROOT / "data" / "level2_staging" / "factors"
    if staging.is_dir():
        local_dirs.append(staging)

    dates = _resolve_dates(
        date=args.date,
        start=args.start,
        end=args.end,
        local_dirs=local_dirs,
        local_only=bool(args.local_only),
        list_remote=list_factor_dates,
    )
    if not dates:
        print("没有可迁移的日期", flush=True)
        return 1

    migrated_dir = out_dir / "_migrated"
    ok = True
    total_rows = 0
    total_stmts = 0
    for index, day in enumerate(dates, start=1):
        marker = migrated_dir / f"{day}.json"
        if not args.force and marker.is_file():
            print(f"[{day}] {index}/{len(dates)} 已迁移，跳过", flush=True)
            continue
        if not args.force and not args.dry_run and d1_client.configured():
            try:
                remote_n = d1_factors.count_day(day)
            except Exception:
                remote_n = 0
            if remote_n > 0:
                print(f"[{day}] {index}/{len(dates)} D1 已有 {remote_n} 行，跳过", flush=True)
                _mark_migrated(marker, day, remote_n, mode="skip-existing")
                continue

        frame = _load_day_frame(day, local_dirs, download_factor_file)
        if frame is None or frame.empty:
            print(f"[{day}] {index}/{len(dates)} 找不到日宽表，跳过", flush=True)
            ok = False
            continue
        rows = d1_factors.dataframe_to_rows(frame, trade_date=day)
        statements = d1_factors.rows_to_literal_insert_statements(rows)
        avg = (len(rows) / len(statements)) if statements else 0.0
        print(
            f"[{day}] {index}/{len(dates)} {len(rows)} 行 -> {len(statements)} 条 SQL"
            f"（均 {avg:.0f} 行/句）",
            flush=True,
        )
        total_rows += len(rows)
        total_stmts += len(statements)
        if args.dry_run:
            continue
        if args.mode == "wrangler":
            out_dir.mkdir(parents=True, exist_ok=True)
            sql_path = out_dir / f"{day}.sql"
            sql_path.write_text(";\n".join(statements) + ";\n", encoding="utf-8")
            print(f"[{day}] 已写 {sql_path}", flush=True)
            print(
                f"  导入示例: npx wrangler d1 execute l2_factors --remote --file={sql_path}",
                flush=True,
            )
            _mark_migrated(marker, day, len(rows), mode="wrangler", statements=len(statements))
        else:
            if not d1_client.configured():
                print(f"[{day}] Worker 未配置，无法 --mode worker", flush=True)
                ok = False
                continue
            try:
                d1_factors.upsert_rows_literal(rows)
            except Exception:
                print(f"[{day}] Worker 写入失败", flush=True)
                ok = False
                continue
            _mark_migrated(marker, day, len(rows), mode="worker", statements=len(statements))
            print(f"[{day}] 已写入 D1", flush=True)

    print(
        f"合计 {total_rows} 行 / {total_stmts} 条 SQL"
        + ("（dry-run）" if args.dry_run else ""),
        flush=True,
    )
    return 0 if ok else 1


def _resolve_dates(
    *,
    date: str,
    start: str,
    end: str,
    local_dirs: list[Path],
    local_only: bool,
    list_remote,
) -> list[str]:
    if date:
        return [str(date)]
    found: set[str] = set()
    for root in local_dirs:
        if not root.is_dir():
            continue
        for path in root.glob("*.parquet"):
            stem = path.stem
            if len(stem) == 8 and stem.isdigit():
                found.add(stem)
    if not local_only:
        try:
            found.update(list_remote())
        except Exception:
            pass
    ordered = sorted(found)
    if start:
        ordered = [day for day in ordered if day >= str(start)]
    if end:
        ordered = [day for day in ordered if day <= str(end)]
    return ordered


def _load_day_frame(day: str, local_dirs: list[Path], download_factor_file):
    import pandas as pd

    for root in local_dirs:
        path = root / f"{day}.parquet"
        if path.is_file():
            return pd.read_parquet(path)
    payload = download_factor_file(day)
    if not payload:
        return None
    from io import BytesIO

    return pd.read_parquet(BytesIO(payload))


def _mark_migrated(
    marker: Path,
    day: str,
    rows: int,
    *,
    mode: str,
    statements: int | None = None,
) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {"date": day, "rows": rows, "mode": mode}
    if statements is not None:
        payload["statements"] = statements
    marker.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
