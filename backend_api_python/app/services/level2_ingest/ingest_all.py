"""按日全量入库云存储：多日严格串行。

阶段 A：先处理所有已解压 local 目录；未达标则停止，不解压任何新 7z。
阶段 B：对剩余 .7z 逐日「整包解压 → 入库 → 达标删 CSV+.7z → 再解下一包」。
禁止先把多个 .7z 都解压完再统一转换。
"""
from __future__ import annotations

import argparse
import traceback
from datetime import datetime, timezone

from . import build_manifest, config, object_store, pipeline
from .convert_local import delete_sources

# 全日 A 股约 1.5 万文件；低于此视为异常，禁止删源
_MIN_EQUITY_FILES = 10_000


def _discover_local_dates(only: list[str] | None = None) -> list[str]:
    """扫描已解压目录 DATA_ROOT/{date}/。"""
    dates = sorted(
        p.name for p in config.DATA_ROOT.iterdir()
        if p.is_dir() and p.name.isdigit() and len(p.name) == 8
    )
    if only:
        dates = [d for d in dates if d in set(only)]
    return dates


def _discover_7z_dates(only: list[str] | None = None) -> list[str]:
    """扫描 DATA_ROOT/*.7z。"""
    dates = sorted(p.stem for p in config.DATA_ROOT.glob("*.7z"))
    if only:
        wanted = set(only)
        missing = wanted - set(dates)
        if missing:
            raise FileNotFoundError(f"找不到归档: {sorted(missing)}")
        dates = [d for d in dates if d in wanted]
    return dates


def _can_delete(stats: dict[str, int]) -> tuple[bool, str]:
    """删除门槛：无失败、上传+跳过=total、total 达到 A 股规模。"""
    failed = int(stats.get("failed", 0))
    total = int(stats.get("total", 0))
    uploaded = int(stats.get("uploaded", 0))
    skipped = int(stats.get("skipped", 0))
    if failed != 0:
        return False, f"failed={failed}"
    if uploaded + skipped != total:
        return False, f"uploaded+skipped={uploaded + skipped} != total={total}"
    if total < _MIN_EQUITY_FILES:
        return False, f"total={total} < {_MIN_EQUITY_FILES}（数量异常）"
    return True, "ok"


def _maybe_delete_sources(date: str, stats: dict[str, int], delete: bool) -> tuple[bool, str]:
    """达标后删除当日 CSV 目录与 .7z，为下一包腾空间。"""
    ok, reason = _can_delete(stats)
    if not delete:
        return False, reason
    if not ok:
        print(f"[{date}] 未删除源文件：{reason}")
        return False, reason
    removed = delete_sources(date, dry_run=False)
    if removed:
        print(f"[{date}] 已删除源文件: {removed}")
        return True, "ok"
    print(f"[{date}] 未删除源文件: 源路径不存在")
    return False, "源路径不存在"


def ingest_local_date(date: str, *, delete: bool) -> dict:
    """从已解压目录入库（阶段 A）。"""
    day_dir = config.DATA_ROOT / date
    if not day_dir.is_dir():
        raise FileNotFoundError(f"未找到已解压目录: {day_dir}")

    print(f"[{date}] 开始入库（local） {day_dir}")
    stats = pipeline.process_local_date(
        date,
        skip_existing=True,
        equities_only=True,
    )
    print(f"[{date}] 完成: {stats}")

    deleted, reason = _maybe_delete_sources(date, stats, delete)
    return {"date": date, "source": "local", "stats": stats, "deleted": deleted, "reason": reason}


def ingest_7z_date(date: str, *, delete: bool) -> dict:
    """整包解压当日 .7z 后入库（阶段 B 单日闭环）。"""
    seven_z = config.DATA_ROOT / f"{date}.7z"
    if not seven_z.exists():
        raise FileNotFoundError(seven_z)

    if not config.local_manifest_path(date).exists():
        print(f"[{date}] 生成 manifest（仅此一次 tar -tf）")
        build_manifest.build(date)

    print(f"[{date}] 开始入库（7z 整包解压） {seven_z}")
    stats = pipeline.process_7z(
        seven_z,
        skip_existing=True,
        equities_only=True,
    )
    print(f"[{date}] 完成: {stats}")

    deleted, reason = _maybe_delete_sources(date, stats, delete)
    return {"date": date, "source": "7z", "stats": stats, "deleted": deleted, "reason": reason}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="全量入库：先 local 全转完，再逐日解压+入库+删源（严格串行）"
    )
    parser.add_argument("--dates", nargs="*", help="仅处理这些交易日")
    parser.add_argument("--no-delete", action="store_true", help="只上传不删 CSV/.7z")
    parser.add_argument("--local-only", action="store_true", help="仅处理已解压目录")
    parser.add_argument("--7z-only", action="store_true", help="仅处理 .7z（跳过 local 阶段）")
    args = parser.parse_args(argv)

    if not object_store.is_configured():
        print(f"存储后端 {object_store.backend()} 未配置，中止")
        return 2

    print(f"入库目标: {object_store.backend()}")

    delete = not args.no_delete
    local_dates = [] if args.__dict__.get("7z_only") else _discover_local_dates(args.dates)
    all_7z = _discover_7z_dates(args.dates)
    # 未解压的日期：有 .7z 但无本地目录（阶段 B）
    local_set = set(local_dates)
    z7_dates = [] if args.__dict__.get("local_only") else [d for d in all_7z if d not in local_set]

    print(
        f"开始入库 local={len(local_dates)} 7z={len(z7_dates)} delete={delete} "
        f"utc={datetime.now(timezone.utc).isoformat()}"
    )
    if local_dates:
        print(f"  阶段A local 优先（转完才解压新包）: {local_dates}")
    if z7_dates:
        print(f"  阶段B 7z 逐日串行: {z7_dates}")

    summary: list[dict] = []

    # 阶段 A：已解压目录必须全部转完；未达标则不解压任何新 7z
    for date in local_dates:
        try:
            rec = ingest_local_date(date, delete=delete)
        except Exception:
            traceback.print_exc()
            print(f"[{date}] 异常退出，停止后续日期（不解压新 7z）")
            break
        summary.append(rec)
        if not _can_delete(rec["stats"])[0]:
            print(f"当日未达标，停止。已处理: {[r['date'] for r in summary]}")
            break
    else:
        # 阶段 B：逐日整包解压 → 入库 → 删源 → 再解下一包
        for date in z7_dates:
            try:
                rec = ingest_7z_date(date, delete=delete)
            except Exception:
                traceback.print_exc()
                print(f"[{date}] 异常退出，停止后续日期")
                break
            summary.append(rec)
            if not _can_delete(rec["stats"])[0]:
                print(f"当日未达标，停止。已处理: {[r['date'] for r in summary]}")
                break

    print("==== 汇总 ====")
    for rec in summary:
        s = rec["stats"]
        print(
            f"{rec['date']} ({rec['source']}) total={s['total']} uploaded={s['uploaded']} "
            f"skipped={s['skipped']} failed={s['failed']} deleted={rec['deleted']}"
        )

    planned = len(local_dates) + len(z7_dates)
    ok_all = len(summary) == planned and all(_can_delete(r["stats"])[0] for r in summary)
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
