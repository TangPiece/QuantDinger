"""基本面 PIT → Canonical（至少 1 个 metric，含 available_time）。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Sequence

import pyarrow as pa

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data.writer import write_pit_fundamental


def _as_utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def synthetic_roe_rows(
    instrument_keys: Sequence[str],
    *,
    available_time: datetime,
    value: float = 12.5,
    data_version: str,
) -> list[dict[str, Any]]:
    """无外部 fundamental 源时生成最小 ROE PIT 行（测试/Golden fixture）。"""
    at = _as_utc(available_time)
    rows: list[dict[str, Any]] = []
    for ik in instrument_keys:
        rows.append(
            {
                "instrument_key": ik,
                "metric_code": "ROE",
                "report_period_start": date(at.year, 1, 1),
                "report_period_end": date(at.year, 3, 31),
                "fiscal_year": at.year,
                "fiscal_quarter": 1,
                "publish_time": at,
                "available_time": at,
                "value": float(value),
                "unit": "pct",
                "currency": "CNY",
                "revision": 0,
                "is_restatement": False,
                "source": "golden_fixture",
                "source_record_id": f"{ik}-ROE-{at.date().isoformat()}",
                "data_version": data_version,
            }
        )
    return rows


def load_roe_from_pg_snapshots(
    instrument_keys: Sequence[str],
    *,
    data_version: str,
) -> list[dict[str, Any]]:
    """尝试从 qd_fundamental_snapshots / 现有服务导出 ROE；失败则返回空。"""
    try:
        from app.utils.db import get_db_connection  # type: ignore
    except Exception:
        return []

    keys = list(instrument_keys)
    if not keys:
        return []
    # 兼容多种表形态：有则读，无则静默空
    sql_candidates = [
        """
        SELECT instrument_key, metric_code, value, available_time, publish_time,
               report_period_start, report_period_end, fiscal_year, fiscal_quarter,
               revision, source, source_record_id
        FROM qd_fundamental_snapshots
        WHERE metric_code IN ('ROE', 'return_on_equity')
          AND instrument_key = ANY(%s)
        """,
    ]
    rows: list[dict[str, Any]] = []
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for sql in sql_candidates:
                    try:
                        cur.execute(sql, (keys,))
                        cols = [d[0] for d in cur.description]
                        for tup in cur.fetchall():
                            item = dict(zip(cols, tup))
                            at = _as_utc(item["available_time"])
                            rows.append(
                                {
                                    "instrument_key": item["instrument_key"],
                                    "metric_code": "ROE",
                                    "report_period_start": item.get("report_period_start")
                                    or date(at.year, 1, 1),
                                    "report_period_end": item.get("report_period_end")
                                    or date(at.year, 3, 31),
                                    "fiscal_year": int(item.get("fiscal_year") or at.year),
                                    "fiscal_quarter": int(item.get("fiscal_quarter") or 1),
                                    "publish_time": _as_utc(item.get("publish_time") or at),
                                    "available_time": at,
                                    "value": float(item["value"]),
                                    "unit": "pct",
                                    "currency": "CNY",
                                    "revision": int(item.get("revision") or 0),
                                    "is_restatement": False,
                                    "source": str(item.get("source") or "pg"),
                                    "source_record_id": str(
                                        item.get("source_record_id") or ""
                                    ),
                                    "data_version": data_version,
                                }
                            )
                        break
                    except Exception:
                        conn.rollback()
                        continue
    except Exception:
        return []
    return rows


def rows_to_pit_table(rows: Sequence[dict[str, Any]]) -> pa.Table:
    """PIT 行 → Arrow 表。"""
    ordered = sorted(
        rows, key=lambda r: (r["instrument_key"], r["metric_code"], r["available_time"])
    )
    if not ordered:
        return pa.table(
            {
                "instrument_key": pa.array([], type=pa.string()),
                "metric_code": pa.array([], type=pa.string()),
                "report_period_start": pa.array([], type=pa.date32()),
                "report_period_end": pa.array([], type=pa.date32()),
                "fiscal_year": pa.array([], type=pa.int32()),
                "fiscal_quarter": pa.array([], type=pa.int32()),
                "publish_time": pa.array([], type=pa.timestamp("us", tz="UTC")),
                "available_time": pa.array([], type=pa.timestamp("us", tz="UTC")),
                "value": pa.array([], type=pa.float64()),
                "unit": pa.array([], type=pa.string()),
                "currency": pa.array([], type=pa.string()),
                "revision": pa.array([], type=pa.int32()),
                "is_restatement": pa.array([], type=pa.bool_()),
                "source": pa.array([], type=pa.string()),
                "source_record_id": pa.array([], type=pa.string()),
                "data_version": pa.array([], type=pa.string()),
            }
        )
    return pa.table(
        {
            "instrument_key": [r["instrument_key"] for r in ordered],
            "metric_code": [r["metric_code"] for r in ordered],
            "report_period_start": pa.array(
                [r["report_period_start"] for r in ordered], type=pa.date32()
            ),
            "report_period_end": pa.array(
                [r["report_period_end"] for r in ordered], type=pa.date32()
            ),
            "fiscal_year": pa.array([int(r["fiscal_year"]) for r in ordered], type=pa.int32()),
            "fiscal_quarter": pa.array(
                [int(r["fiscal_quarter"]) for r in ordered], type=pa.int32()
            ),
            "publish_time": [_as_utc(r["publish_time"]) for r in ordered],
            "available_time": [_as_utc(r["available_time"]) for r in ordered],
            "value": [float(r["value"]) for r in ordered],
            "unit": [r["unit"] for r in ordered],
            "currency": [r["currency"] for r in ordered],
            "revision": pa.array([int(r["revision"]) for r in ordered], type=pa.int32()),
            "is_restatement": [bool(r["is_restatement"]) for r in ordered],
            "source": [r["source"] for r in ordered],
            "source_record_id": [r["source_record_id"] for r in ordered],
            "data_version": [r["data_version"] for r in ordered],
        }
    )


def ingest_pit_fundamental(
    store: CanonicalStore,
    *,
    instrument_keys: Sequence[str],
    version: str,
    registry: ResearchRegistry | None = None,
    exchange: str = "CN",
    rows: Sequence[dict[str, Any]] | None = None,
    allow_synthetic: bool = True,
) -> dict[str, Any]:
    """写入 PIT fundamental；优先 PG/注入行，否则合成 ROE。"""
    payload = list(rows) if rows is not None else load_roe_from_pg_snapshots(
        instrument_keys, data_version=version
    )
    source = "injected_or_pg"
    if not payload and allow_synthetic:
        payload = synthetic_roe_rows(
            instrument_keys,
            available_time=datetime(2024, 4, 30, 15, 0, tzinfo=timezone.utc),
            data_version=version,
        )
        source = "synthetic"
    if not payload:
        return {"written": [], "row_count": 0, "source": "empty"}

    by_year: dict[int, list[dict[str, Any]]] = {}
    for row in payload:
        year = _as_utc(row["available_time"]).year
        by_year.setdefault(year, []).append(row)

    written: list[dict[str, Any]] = []
    for year, part in sorted(by_year.items()):
        meta = write_pit_fundamental(
            store,
            rows_to_pit_table(part),
            exchange=exchange,
            year=year,
            registry=registry,
            version=version,
        )
        written.append(meta)
    return {"written": written, "row_count": len(payload), "source": source}
