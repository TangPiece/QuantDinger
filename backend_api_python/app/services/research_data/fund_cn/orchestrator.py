"""End-to-end fund_cn pipeline: stage → PIT → daily factors → publish."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from app.services.research_data.canonical_store import CanonicalStore, LocalCanonicalStore
from app.services.research_data.registry import LocalJsonRegistry, ResearchRegistry

from .adapters.announce import StaticAnnounceAdapter
from .adapters.akshare_adapter import AkshareStatementAdapter
from .adapters.base import (
    AnnounceAdapter,
    AnnounceRow,
    ShareCapitalAdapter,
    ShareCapitalRow,
    StatementAdapter,
    StatementFieldRow,
)
from .compute import build_daily_factor_panel
from .coverage import coverage_summary
from .ingest import build_pit_rows_from_staging, publish_pit_from_staging, stage_from_adapters
from . import meta
from .paths_local import default_factor_root, default_staging_root
from .publish import publish_day_panel
from .register import register_mvp_factors
from .staging import (
    read_announce_rows,
    read_share_capital_rows,
    read_statement_rows,
    staging_source_version,
    write_marker,
    write_share_capital_rows,
)

_log = logging.getLogger(__name__)


def run_stage(
    instrument_keys: Sequence[str],
    *,
    statement_adapter: StatementAdapter | None = None,
    announce_adapter: AnnounceAdapter | None = None,
    statement_rows: Sequence[StatementFieldRow] | None = None,
    announce_rows: Sequence[AnnounceRow] | None = None,
    share_capital_adapter: ShareCapitalAdapter | None = None,
    share_capital_rows: Sequence[ShareCapitalRow] | None = None,
    root: Path | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    """Stage statements, disclosure calendar and share-capital events.

    Without an explicit announce adapter, a statement adapter exposing
    ``fetch_announcements`` (Eastmoney NOTICE_DATE) is reused as the calendar.
    """
    stmts = list(statement_rows) if statement_rows is not None else []
    anns = list(announce_rows) if announce_rows is not None else []
    adapter: Any = None
    if statement_rows is None:
        adapter = statement_adapter or AkshareStatementAdapter()
        stmts = adapter.fetch_statements(instrument_keys, start=start, end=end)
    if announce_rows is None:
        adapter_a = announce_adapter
        if adapter_a is None and hasattr(adapter, "fetch_announcements"):
            adapter_a = adapter
        adapter_a = adapter_a or StaticAnnounceAdapter([])
        anns = adapter_a.fetch_announcements(instrument_keys, start=start, end=end)
    info = stage_from_adapters(stmts, anns, root=root)
    shares: list[ShareCapitalRow] = list(share_capital_rows or [])
    if share_capital_rows is None and share_capital_adapter is not None:
        shares = share_capital_adapter.fetch_share_capital(instrument_keys)
    if share_capital_rows is not None or share_capital_adapter is not None:
        write_share_capital_rows(shares, root=root)
    info["share_capital_rows"] = len(shares)
    return info


def run_coverage(root: Path | None = None) -> dict[str, Any]:
    statements = read_statement_rows(root)
    announce = read_announce_rows(root)
    summary = coverage_summary(statements, announce)
    write_marker("coverage", summary, root=root)
    return summary


def run_pit_publish(
    *,
    store: CanonicalStore | None = None,
    root: Path | None = None,
    registry: ResearchRegistry | None = None,
    exchange: str = "CN",
) -> dict[str, Any]:
    source_version = staging_source_version(root)
    job_id = meta.create_job("pit_publish", source_version=source_version)
    meta.seed_definitions()
    try:
        result = publish_pit_from_staging(
            store or LocalCanonicalStore(),
            root=root,
            registry=registry,
            exchange=exchange,
        )
        meta.finish_job(job_id, status="done", rows_processed=int(result.get("row_count") or 0))
        meta.upsert_period_status(
            source_version,
            "pit_publish",
            source_version=source_version,
            status="done",
        )
        return result
    except Exception as exc:
        meta.finish_job(job_id, status="failed", error_message=str(exc))
        meta.upsert_period_status(
            source_version,
            "pit_publish",
            source_version=source_version,
            status="failed",
            error_message=str(exc),
        )
        raise


def run_compute_publish(
    trading_dates: Sequence[date | str],
    instrument_keys: Sequence[str],
    market: pd.DataFrame | None = None,
    *,
    pit_rows: Sequence[dict[str, Any]] | None = None,
    root: Path | None = None,
    factor_root: Path | None = None,
    store: CanonicalStore | None = None,
    registry: ResearchRegistry | None = None,
    mvp_only: bool = True,
    upload: bool = True,
) -> dict[str, Any]:
    rows = list(pit_rows) if pit_rows is not None else build_pit_rows_from_staging(root)
    panel = build_daily_factor_panel(
        rows,
        trading_dates,
        instrument_keys,
        market,
        mvp_only=mvp_only,
        share_capital=read_share_capital_rows(root),
    )
    published: list[dict[str, Any]] = []
    canonical = store or LocalCanonicalStore()
    froot = factor_root or default_factor_root()
    if panel.empty:
        return {"days": [], "row_count": 0, "panel_columns": list(panel.columns)}

    for day, part in panel.groupby("trading_date"):
        meta_row = publish_day_panel(
            part.reset_index(drop=True),
            str(day),
            store=canonical,
            factor_root=froot,
            registry=registry,
            upload=upload,
        )
        if meta_row.get("storage_uri"):
            meta.register_dataset(
                str(meta_row["storage_uri"]),
                row_count=int(meta_row.get("row_count") or 0),
            )
        published.append(meta_row)
    write_marker(
        "factor_publish",
        {"status": "done", "days": len(published), "row_count": int(len(panel))},
        root=root,
    )
    return {"days": published, "row_count": int(len(panel)), "panel_columns": list(panel.columns)}


def run_register(
    registry: ResearchRegistry | None = None,
    *,
    root: Path | None = None,
    require_coverage: bool = False,
) -> list[str]:
    reg = registry or LocalJsonRegistry()
    summary = run_coverage(root) if require_coverage else None
    return register_mvp_factors(reg, coverage_summary=summary, require_coverage=require_coverage)


def run_pipeline(
    instrument_keys: Sequence[str],
    trading_dates: Sequence[date | str],
    *,
    statement_rows: Sequence[StatementFieldRow] | None = None,
    announce_rows: Sequence[AnnounceRow] | None = None,
    share_capital_rows: Sequence[ShareCapitalRow] | None = None,
    market: pd.DataFrame | None = None,
    root: Path | None = None,
    store: CanonicalStore | None = None,
    registry: ResearchRegistry | None = None,
    mvp_only: bool = True,
    register: bool = True,
    require_coverage: bool = True,
) -> dict[str, Any]:
    """Full offline-friendly pipeline (inject rows for tests; live adapters for prod).

    PIT_SAFE registration is coverage-gated by default.
    """
    staging_root = root or default_staging_root()
    stage_info = run_stage(
        instrument_keys,
        statement_rows=statement_rows,
        announce_rows=announce_rows,
        share_capital_rows=share_capital_rows,
        root=staging_root,
    )
    coverage = run_coverage(staging_root)
    canonical = store or LocalCanonicalStore()
    reg = registry or LocalJsonRegistry()
    pit = run_pit_publish(store=canonical, root=staging_root, registry=reg)
    factors = run_compute_publish(
        trading_dates,
        instrument_keys,
        market,
        root=staging_root,
        store=canonical,
        registry=reg,
        mvp_only=mvp_only,
    )
    registered: list[str] = []
    if register:
        try:
            registered = run_register(reg, root=staging_root, require_coverage=require_coverage)
        except Exception as exc:
            _log.warning("factor lab register soft-fail: %s", exc)
    return {
        "stage": stage_info,
        "coverage": coverage,
        "pit": pit,
        "factors": factors,
        "registered": registered,
    }
