"""停牌/涨跌停 → Canonical trading_status（无源则写空分区）。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Sequence

import pyarrow as pa

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data.writer import write_trading_status


def empty_status_table() -> pa.Table:
    """空 trading_status 表（schema 齐全）。"""
    return pa.table(
        {
            "instrument_key": pa.array([], type=pa.string()),
            "trading_date": pa.array([], type=pa.date32()),
            "status": pa.array([], type=pa.string()),
            "is_suspended": pa.array([], type=pa.bool_()),
            "is_limit_up": pa.array([], type=pa.bool_()),
            "is_limit_down": pa.array([], type=pa.bool_()),
            "upper_limit": pa.array([], type=pa.float64()),
            "lower_limit": pa.array([], type=pa.float64()),
            "data_version": pa.array([], type=pa.string()),
        }
    )


def rows_to_status_table(rows: Sequence[dict[str, Any]]) -> pa.Table:
    if not rows:
        return empty_status_table()
    ordered = sorted(rows, key=lambda r: (r["instrument_key"], r["trading_date"]))
    return pa.table(
        {
            "instrument_key": [r["instrument_key"] for r in ordered],
            "trading_date": pa.array([r["trading_date"] for r in ordered], type=pa.date32()),
            "status": [r["status"] for r in ordered],
            "is_suspended": [bool(r.get("is_suspended", False)) for r in ordered],
            "is_limit_up": [bool(r.get("is_limit_up", False)) for r in ordered],
            "is_limit_down": [bool(r.get("is_limit_down", False)) for r in ordered],
            "upper_limit": [float(r["upper_limit"]) if r.get("upper_limit") is not None else None for r in ordered],
            "lower_limit": [float(r["lower_limit"]) if r.get("lower_limit") is not None else None for r in ordered],
            "data_version": [r["data_version"] for r in ordered],
        }
    )


def ingest_trading_status(
    store: CanonicalStore,
    *,
    version: str,
    registry: ResearchRegistry | None = None,
    exchange: str = "CN",
    rows: Sequence[dict[str, Any]] | None = None,
    placeholder_year: int = 2024,
    placeholder_month: int = 1,
) -> dict[str, Any]:
    """写入 trading_status；无行时写一个空分区并标明 empty。"""
    payload = list(rows or [])
    if not payload:
        meta = write_trading_status(
            store,
            empty_status_table(),
            exchange=exchange,
            year=placeholder_year,
            month=placeholder_month,
            registry=registry,
            version=version,
        )
        return {
            "written": [meta],
            "row_count": 0,
            "source": "empty_partition",
            "note": "no trading_status source; empty partition written",
        }

    by_ym: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in payload:
        td: date = row["trading_date"]
        by_ym[(td.year, td.month)].append(row)

    written: list[dict[str, Any]] = []
    for (year, month), part in sorted(by_ym.items()):
        meta = write_trading_status(
            store,
            rows_to_status_table(part),
            exchange=exchange,
            year=year,
            month=month,
            registry=registry,
            version=version,
        )
        written.append(meta)
    return {"written": written, "row_count": len(payload), "source": "injected"}
