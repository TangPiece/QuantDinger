"""Staging → Canonical pit_fundamental (append-only revisions)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from app.services.research_data.canonical_store import CanonicalStore, LocalCanonicalStore
from app.services.research_data.ingest.fundamental_pit import ingest_pit_fundamental
from app.services.research_data.registry import ResearchRegistry

from .adapters.base import AnnounceRow, StatementFieldRow
from .metrics import statements_to_pit_metrics
from .staging import (
    read_announce_rows,
    read_statement_rows,
    staging_source_version,
    write_announce_rows,
    write_marker,
    write_statement_rows,
)


def stage_from_adapters(
    statement_rows: Sequence[StatementFieldRow],
    announce_rows: Sequence[AnnounceRow],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    stmt_path = write_statement_rows(statement_rows, root=root)
    ann_path = write_announce_rows(announce_rows, root=root)
    version = staging_source_version(root)
    write_marker(
        "stage",
        {
            "status": "done",
            "source_version": version,
            "statement_rows": len(statement_rows),
            "announce_rows": len(announce_rows),
            "statements_path": str(stmt_path),
            "announce_path": str(ann_path),
        },
        root=root,
    )
    return {
        "source_version": version,
        "statement_rows": len(statement_rows),
        "announce_rows": len(announce_rows),
        "statements_path": str(stmt_path),
        "announce_path": str(ann_path),
    }


def build_pit_rows_from_staging(root: Path | None = None) -> list[dict[str, Any]]:
    statements = read_statement_rows(root)
    announce = read_announce_rows(root)
    return statements_to_pit_metrics(statements, announce)


def publish_pit_from_staging(
    store: CanonicalStore | None = None,
    *,
    root: Path | None = None,
    registry: ResearchRegistry | None = None,
    exchange: str = "CN",
    data_version: str | None = None,
    instrument_keys: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Convert staged statements into Canonical PIT; append-only via new data_version."""
    rows = build_pit_rows_from_staging(root)
    if instrument_keys is not None:
        wanted = set(instrument_keys)
        rows = [r for r in rows if r["instrument_key"] in wanted]
    version = data_version or f"fund_cn.{staging_source_version(root)}"
    for row in rows:
        row["data_version"] = version

    canonical = store or LocalCanonicalStore()
    keys = sorted({r["instrument_key"] for r in rows})
    result = ingest_pit_fundamental(
        canonical,
        instrument_keys=keys,
        version=version,
        registry=registry,
        exchange=exchange,
        rows=rows,
        allow_synthetic=False,
    )
    write_marker(
        "pit_publish",
        {
            "status": "done",
            "data_version": version,
            "row_count": result.get("row_count", 0),
            "written": result.get("written", []),
            "source": result.get("source"),
        },
        root=root,
    )
    return result


def append_restatement(
    store: CanonicalStore,
    *,
    base_rows: Sequence[dict[str, Any]],
    revision: int,
    available_time,
    values: dict[str, float],
    data_version: str,
    registry: ResearchRegistry | None = None,
    exchange: str = "CN",
) -> dict[str, Any]:
    """Append restated metrics without overwriting prior revisions."""
    payload: list[dict[str, Any]] = []
    for row in base_rows:
        metric = row["metric_code"]
        if metric not in values:
            continue
        updated = dict(row)
        updated["value"] = float(values[metric])
        updated["revision"] = int(revision)
        updated["is_restatement"] = True
        updated["available_time"] = available_time
        updated["publish_time"] = available_time
        updated["data_version"] = data_version
        updated["source_record_id"] = f"{row['instrument_key']}:{metric}:{row['report_period_end']}:r{revision}"
        payload.append(updated)
    return ingest_pit_fundamental(
        store,
        instrument_keys=sorted({r["instrument_key"] for r in payload}),
        version=data_version,
        registry=registry,
        exchange=exchange,
        rows=payload,
        allow_synthetic=False,
    )

