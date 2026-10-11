"""按日×组增量编排：计算 → 合并写盘 → R2 → D1 元数据。"""
from __future__ import annotations

import logging
from pathlib import Path

from . import meta, status, storage
from .catalog import ALL_GROUPS, FACTOR_VERSION, factor_ids_for_group, schema_hash
from .engine import calc_group_day, list_codes

_log = logging.getLogger(__name__)


def run(
    dates: list[str],
    *,
    parquet_root: Path,
    output_root: Path | None = None,
    groups: list[str] | None = None,
    force: bool = False,
    factor_version: int = FACTOR_VERSION,
    upload_r2: bool = True,
    seed_defs: bool = True,
    compact_months: bool = True,
) -> dict[str, object]:
    """执行增量计算。返回摘要。"""
    root = Path(output_root) if output_root is not None else storage.default_root()
    root.mkdir(parents=True, exist_ok=True)
    books = Path(parquet_root)
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
                    parquet_root=books,
                    output_root=root,
                    force=force,
                    factor_version=factor_version,
                    upload_r2=upload_r2,
                )
                if result["status"] == "skipped":
                    summary["skipped"] = int(summary["skipped"]) + 1
                elif result["status"] in ("done", "partial"):
                    summary["processed"] = int(summary["processed"]) + 1
                    job_rows += int(result.get("symbol_ok") or 0)
                    summary["rows"] = int(summary["rows"]) + int(result.get("symbol_ok") or 0)
                    touched_months.add(str(trade_date)[:6])
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

    if compact_months:
        for yyyymm in sorted(touched_months):
            # 仅当月内本地日文件齐全时 compact；不强制删日文件
            try:
                storage.compact_month(root, yyyymm, factor_version=factor_version, delete_days=False)
            except Exception:
                _log.warning("月 compact 失败 %s", yyyymm, exc_info=True)

    return summary


def process_day_group(
    trade_date: str,
    factor_group: str,
    *,
    parquet_root: Path,
    output_root: Path,
    force: bool = False,
    factor_version: int = FACTOR_VERSION,
    upload_r2: bool = True,
) -> dict[str, object]:
    codes = list_codes(parquet_root, trade_date)
    source_version = status.source_version_for_date(
        parquet_root, trade_date, factor_group, codes=codes
    )
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

    rows, status_rows, ok, fail = calc_group_day(
        parquet_root, trade_date, factor_group, codes=codes
    )
    for item in status_rows:
        item["source_version"] = source_version

    existing = storage.read_day(output_root, trade_date, factor_version=factor_version)
    group_columns = factor_ids_for_group(factor_group)
    merged = storage.merge_group_columns(existing, rows, group_columns, trade_date)
    storage.write_day(output_root, trade_date, merged, factor_version=factor_version)
    storage.write_status(output_root, trade_date, status_rows, factor_version=factor_version)

    uri = None
    if upload_r2:
        uri = storage.upload_day_to_r2(output_root, trade_date, factor_version=factor_version)
    if uri is None:
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
