"""公司行为 / 后复权因子 → Canonical corporate_action。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Sequence

import pyarrow as pa

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data.writer import write_corporate_action


def synthetic_split_rows(
    instrument_keys: Sequence[str],
    *,
    effective_date: date,
    split_ratio: float = 1.1,
    data_version: str,
) -> list[dict[str, Any]]:
    """最小后复权支撑：每个标的一条 split 事件（split_ratio 即价格乘数）。"""
    rows: list[dict[str, Any]] = []
    for ik in instrument_keys:
        rows.append(
            {
                "instrument_key": ik,
                "effective_date": effective_date,
                "action_type": "split",
                "cash_dividend": 0.0,
                "split_ratio": float(split_ratio),
                "rights_ratio": 0.0,
                "rights_price": 0.0,
                "currency": "CNY",
                "source": "golden_fixture",
                "source_version": data_version,
                "data_version": data_version,
            }
        )
    return rows


def rows_to_ca_table(rows: Sequence[dict[str, Any]]) -> pa.Table:
    """CA 行 → Arrow 表。"""
    ordered = sorted(rows, key=lambda r: (r["instrument_key"], r["effective_date"]))
    if not ordered:
        return pa.table(
            {
                "instrument_key": pa.array([], type=pa.string()),
                "effective_date": pa.array([], type=pa.date32()),
                "action_type": pa.array([], type=pa.string()),
                "cash_dividend": pa.array([], type=pa.float64()),
                "split_ratio": pa.array([], type=pa.float64()),
                "rights_ratio": pa.array([], type=pa.float64()),
                "rights_price": pa.array([], type=pa.float64()),
                "currency": pa.array([], type=pa.string()),
                "source": pa.array([], type=pa.string()),
                "source_version": pa.array([], type=pa.string()),
                "data_version": pa.array([], type=pa.string()),
            }
        )
    return pa.table(
        {
            "instrument_key": [r["instrument_key"] for r in ordered],
            "effective_date": pa.array(
                [r["effective_date"] for r in ordered], type=pa.date32()
            ),
            "action_type": [r["action_type"] for r in ordered],
            "cash_dividend": [float(r.get("cash_dividend") or 0.0) for r in ordered],
            "split_ratio": [float(r.get("split_ratio") or 1.0) for r in ordered],
            "rights_ratio": [float(r.get("rights_ratio") or 0.0) for r in ordered],
            "rights_price": [float(r.get("rights_price") or 0.0) for r in ordered],
            "currency": [r.get("currency") or "CNY" for r in ordered],
            "source": [r.get("source") or "" for r in ordered],
            "source_version": [r.get("source_version") or "" for r in ordered],
            "data_version": [r["data_version"] for r in ordered],
        }
    )


def ingest_corporate_actions(
    store: CanonicalStore,
    *,
    version: str,
    registry: ResearchRegistry | None = None,
    exchange: str = "CN",
    rows: Sequence[dict[str, Any]] | None = None,
    instrument_keys: Sequence[str] | None = None,
    allow_synthetic: bool = True,
) -> dict[str, Any]:
    """写入 CA；无源时可为 Golden 合成一条 split。"""
    payload = list(rows or [])
    source = "injected"
    if not payload and allow_synthetic and instrument_keys:
        payload = synthetic_split_rows(
            instrument_keys,
            effective_date=date(2024, 6, 1),
            split_ratio=1.1,
            data_version=version,
        )
        source = "synthetic"
    if not payload:
        return {"written": [], "row_count": 0, "source": "empty"}

    by_year: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in payload:
        by_year[row["effective_date"].year].append(row)

    written: list[dict[str, Any]] = []
    for year, part in sorted(by_year.items()):
        meta = write_corporate_action(
            store,
            rows_to_ca_table(part),
            exchange=exchange,
            year=year,
            registry=registry,
            version=version,
        )
        written.append(meta)
    return {"written": written, "row_count": len(payload), "source": source}
