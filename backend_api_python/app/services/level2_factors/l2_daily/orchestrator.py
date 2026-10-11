"""按日×组增量编排：解压(可选) → 计算 → 合并写盘 → R2 → D1 元数据。"""
from __future__ import annotations

import logging
from pathlib import Path

from . import meta, prepare, status, storage
from .catalog import ALL_GROUPS, FACTOR_VERSION, factor_ids_for_group, schema_hash
from .engine import calc_group_day, list_codes

_log = logging.getLogger(__name__)


def run(
    dates: list[str],
    *,
    books_root: Path | None = None,
    parquet_root: Path | None = None,
    output_root: Path | None = None,
    groups: list[str] | None = None,
    force: bool = False,
    factor_version: int = FACTOR_VERSION,
    upload_r2: bool = True,
    seed_defs: bool = True,
    compact_months: bool = True,
) -> dict[str, object]:
    """执行增量计算。返回摘要。

    ``books_root`` 为明细根（CSV 或 Parquet）。``parquet_root`` 为兼容旧参数名的别名。
    """
    root = Path(output_root) if output_root is not None else storage.default_root()
    root.mkdir(parents=True, exist_ok=True)
    books = Path(books_root if books_root is not None else parquet_root or prepare.default_raw_root())
    selected_groups = list(groups) if groups else list(ALL_GROUPS)
    ordered_dates = sorted({str(d) for d in dates if str(d).isdigit() and len(str(d)) == 8})

    if seed_defs:
        try:
            meta.seed_definitions(factor_version=factor_version)
        except Exception:
            _log.warning("l2_daily 种子定义失败（继续本地计算）", exc_info=True)

    summary = {
        "dates": ordered_dates,
        "groups": selected_groups,
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "rows": 0,
    }
    touched_months: set[str] = set()
    dates_to_upload: set[str] = set()

    for factor_group in selected_groups:
        if not ordered_dates:
            break
        job_id = meta.create_job(
            factor_group=factor_group,
            start_date=ordered_dates[0],
            end_date=ordered_dates[-1],
            factor_version=factor_version,
        )
        job_rows = 0
        job_error: str | None = None
        try:
            for trade_date in ordered_dates:
                result = process_day_group(
                    trade_date,
                    factor_group,
                    books_root=books,
                    output_root=root,
                    force=force,
                    factor_version=factor_version,
                )
                if result["status"] == "skipped":
                    summary["skipped"] = int(summary["skipped"]) + 1
                elif result["status"] in ("done", "partial"):
                    summary["processed"] = int(summary["processed"]) + 1
                    job_rows += int(result.get("symbol_ok") or 0)
                    summary["rows"] = int(summary["rows"]) + int(result.get("symbol_ok") or 0)
                    touched_months.add(str(trade_date)[:6])
                    dates_to_upload.add(str(trade_date))
                else:
                    summary["failed"] = int(summary["failed"]) + 1
                    job_error = str(result.get("error") or job_error or "group failed")
            meta.finish_job(
                job_id,
                status="failed" if job_error and not job_rows else "done",
                rows_processed=job_rows,
                error_message=job_error,
            )
        except Exception as exc:
            _log.exception("l2_daily job 失败 %s", factor_group)
            meta.finish_job(job_id, status="failed", rows_processed=job_rows, error_message=str(exc))
            summary["failed"] = int(summary["failed"]) + 1

    # 所选因子组全部算完后再按日上传一次
    if upload_r2:
        for trade_date in sorted(dates_to_upload):
            try:
                uri = storage.upload_day_to_r2(root, trade_date, factor_version=factor_version)
                if uri:
                    print(f"[{trade_date}] uploaded {uri}", flush=True)
            except Exception:
                _log.warning("l2_daily 日终上传失败 %s", trade_date, exc_info=True)

    if compact_months:
        for yyyymm in sorted(touched_months):
            try:
                storage.compact_month(root, yyyymm, factor_version=factor_version, delete_days=False)
            except Exception:
                _log.warning("月 compact 失败 %s", yyyymm, exc_info=True)

    return summary


def run_batch(
    *,
    raw_root: Path | None = None,
    output_root: Path | None = None,
    groups: list[str] | None = None,
    dates: list[str] | None = None,
    force: bool = False,
    factor_version: int = FACTOR_VERSION,
    upload_r2: bool = True,
    seed_defs: bool = True,
    compact_months: bool = True,
    delete_sources: bool = True,
    dry_run: bool = False,
    local_only: bool = False,
    z7_only: bool = False,
) -> dict[str, object]:
    """扫描 raw：阶段 A 已解压 CSV，阶段 B 逐日解压；算百因子后可选删源。"""
    root = Path(raw_root) if raw_root is not None else prepare.default_raw_root()
    only = list(dates) if dates else None
    local_dates = [] if z7_only else prepare.discover_local_dates(root, only)
    all_7z = prepare.discover_7z_dates(root, only)
    local_set = set(local_dates)
    z7_dates = [] if local_only else [d for d in all_7z if d not in local_set]

    # 显式 dates 时：本地与 7z 都没有的日期仍排入计划，由 ensure_day_csv 失败并停后续
    if only:
        planned = sorted(set(only))
        if local_only:
            planned = [d for d in planned if d in local_set]
        elif z7_only:
            planned = [d for d in planned if d in set(all_7z)]
        else:
            # 已解压优先，其余按 only 顺序走解压/失败
            planned = [d for d in planned if d in local_set] + [
                d for d in planned if d not in local_set
            ]
    else:
        planned = local_dates + z7_dates

    print(
        f"l2_daily batch raw={root} local={len(local_dates)} 7z={len(z7_dates)} "
        f"planned={len(planned)} delete={delete_sources} dry_run={dry_run}",
        flush=True,
    )
    if local_dates:
        print(f"  阶段A local CSV: {local_dates}", flush=True)
    if z7_dates:
        print(f"  阶段B 7z 串行: {z7_dates}", flush=True)

    summary = {
        "dates": [],
        "groups": list(groups) if groups else list(ALL_GROUPS),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "rows": 0,
        "deleted": [],
    }
    if not planned:
        print("无可处理日期", flush=True)
        summary["failed"] = 1
        return summary

    for trade_date in planned:
        try:
            prepare.ensure_day_csv(trade_date, root, dry_run=dry_run)
        except Exception as exc:
            _log.exception("准备 CSV 失败 %s", trade_date)
            print(f"[{trade_date}] 准备失败: {exc}，停止后续", flush=True)
            summary["failed"] = int(summary["failed"]) + 1
            break

        if dry_run:
            codes = list_codes(root, trade_date)
            print(f"[{trade_date}] dry-run symbols={len(codes)}", flush=True)
            summary["dates"].append(trade_date)  # type: ignore[union-attr]
            summary["skipped"] = int(summary["skipped"]) + 1
            continue

        day_summary = run(
            [trade_date],
            books_root=root,
            output_root=output_root,
            groups=groups,
            force=force,
            factor_version=factor_version,
            upload_r2=upload_r2,
            seed_defs=seed_defs,
            compact_months=compact_months,
        )
        summary["dates"].append(trade_date)  # type: ignore[union-attr]
        summary["processed"] = int(summary["processed"]) + int(day_summary.get("processed") or 0)
        summary["skipped"] = int(summary["skipped"]) + int(day_summary.get("skipped") or 0)
        summary["failed"] = int(summary["failed"]) + int(day_summary.get("failed") or 0)
        summary["rows"] = int(summary["rows"]) + int(day_summary.get("rows") or 0)

        day_failed = int(day_summary.get("failed") or 0)
        day_ok = int(day_summary.get("processed") or 0) + int(day_summary.get("skipped") or 0)
        if day_failed > 0 and int(day_summary.get("processed") or 0) == 0:
            print(f"[{trade_date}] 当日失败，停止后续解压", flush=True)
            break
        if delete_sources and day_failed == 0 and day_ok > 0:
            removed = prepare.delete_day_sources(trade_date, root, dry_run=False)
            summary["deleted"].extend(removed)  # type: ignore[union-attr]
            print(f"[{trade_date}] 已删源 {removed}", flush=True)
        # 仅第一日之后不再重复 seed
        seed_defs = False

    return summary


def process_day_group(
    trade_date: str,
    factor_group: str,
    *,
    books_root: Path | None = None,
    parquet_root: Path | None = None,
    output_root: Path,
    force: bool = False,
    factor_version: int = FACTOR_VERSION,
) -> dict[str, object]:
    """计算并合并一组到本地日宽表；不上传 R2（由 run 日终统一上传）。"""
    books = Path(books_root if books_root is not None else parquet_root or prepare.default_raw_root())
    codes = list_codes(books, trade_date)
    source_version = status.source_version_for_date(books, trade_date, factor_group, codes=codes)
    local = status.read_local_marker(output_root, trade_date, factor_group)
    if status.should_skip(
        trade_date,
        factor_group,
        source_version,
        force=force,
        factor_version=factor_version,
        local_status=local,
    ):
        return {"status": "skipped", "trade_date": trade_date, "factor_group": factor_group}

    if not codes:
        _mark(
            trade_date,
            factor_group,
            source_version=source_version,
            status_name="skipped",
            symbol_ok=0,
            symbol_fail=0,
            factor_version=factor_version,
            output_root=output_root,
            error_message="no symbols",
        )
        return {
            "status": "skipped",
            "trade_date": trade_date,
            "factor_group": factor_group,
            "error": "no symbols",
        }

    rows, status_rows, ok, fail = calc_group_day(books, trade_date, factor_group, codes=codes)
    for item in status_rows:
        item["source_version"] = source_version

    existing = storage.read_day(output_root, trade_date, factor_version=factor_version)
    group_columns = factor_ids_for_group(factor_group)
    merged = storage.merge_group_columns(existing, rows, group_columns, trade_date)
    storage.write_day(output_root, trade_date, merged, factor_version=factor_version)
    storage.write_status(output_root, trade_date, status_rows, factor_version=factor_version)

    uri = storage.logical_day_key(trade_date, factor_version=factor_version)
    day_status = "done" if fail == 0 and ok > 0 else ("partial" if ok > 0 else "failed")
    _mark(
        trade_date,
        factor_group,
        source_version=source_version,
        status_name=day_status,
        symbol_ok=ok,
        symbol_fail=fail,
        factor_version=factor_version,
        output_root=output_root,
        error_message=None if ok else "all symbols failed",
    )
    try:
        meta.upsert_dataset(
            dataset_id=meta.dataset_id_for(trade_date, factor_group, factor_version),
            factor_group=factor_group,
            source_version=source_version,
            start_date=trade_date,
            end_date=trade_date,
            storage_uri=uri,
            schema_hash=schema_hash(),
            row_count=len(merged),
            status="ready" if day_status in ("done", "partial") else "failed",
            factor_version=factor_version,
        )
    except Exception:
        _log.warning("登记 dataset 失败 %s %s", trade_date, factor_group, exc_info=True)

    return {
        "status": day_status,
        "trade_date": trade_date,
        "factor_group": factor_group,
        "symbol_ok": ok,
        "symbol_fail": fail,
        "storage_uri": uri,
    }


def _mark(
    trade_date: str,
    factor_group: str,
    *,
    source_version: str,
    status_name: str,
    symbol_ok: int,
    symbol_fail: int,
    factor_version: int,
    output_root: Path,
    error_message: str | None,
) -> None:
    status.write_local_marker(
        output_root,
        trade_date,
        factor_group,
        source_version=source_version,
        status=status_name,
        symbol_ok=symbol_ok,
        symbol_fail=symbol_fail,
        factor_version=factor_version,
    )
    try:
        meta.upsert_day_status(
            trade_date=trade_date,
            factor_group=factor_group,
            source_version=source_version,
            status=status_name,
            symbol_ok=symbol_ok,
            symbol_fail=symbol_fail,
            schema_hash=schema_hash(),
            error_message=error_message,
            factor_version=factor_version,
        )
    except Exception:
        _log.warning("写 day_status 失败 %s %s", trade_date, factor_group, exc_info=True)
