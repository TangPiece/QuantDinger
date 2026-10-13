"""D1 research registry metadata for fund_cn jobs (soft-fail; values stay on R2)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.research_data import d1_client

from .catalog import FACTOR_DEFINITIONS, FACTOR_SET, FACTOR_VERSION, schema_hash

_log = logging.getLogger(__name__)

_SCHEMA_SQL = [
    """
CREATE TABLE IF NOT EXISTS fund_cn_factor_definitions (
  factor_id TEXT PRIMARY KEY,
  factor_name TEXT NOT NULL,
  display_name TEXT,
  category TEXT NOT NULL,
  kind TEXT NOT NULL,
  formula TEXT,
  mvp INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 0,
  information_policy TEXT NOT NULL,
  raw_ok TEXT NOT NULL,
  compute_ok TEXT NOT NULL,
  pit_ok TEXT NOT NULL,
  factor_version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
)
""".strip(),
    """
CREATE TABLE IF NOT EXISTS fund_cn_factor_jobs (
  job_id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  factor_version INTEGER NOT NULL,
  status TEXT NOT NULL,
  source_version TEXT,
  rows_processed INTEGER DEFAULT 0,
  error_message TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
""".strip(),
    """
CREATE TABLE IF NOT EXISTS fund_cn_factor_datasets (
  dataset_id TEXT PRIMARY KEY,
  factor_set TEXT NOT NULL,
  factor_version INTEGER NOT NULL,
  storage_uri TEXT NOT NULL,
  schema_hash TEXT NOT NULL,
  row_count INTEGER,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
)
""".strip(),
    """
CREATE TABLE IF NOT EXISTS fund_cn_period_status (
  period_key TEXT NOT NULL,
  job_type TEXT NOT NULL,
  factor_version INTEGER NOT NULL,
  source_version TEXT NOT NULL,
  status TEXT NOT NULL,
  error_message TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (period_key, job_type, factor_version)
)
""".strip(),
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_schema() -> bool:
    if not d1_client.configured():
        return False
    try:
        for sql in _SCHEMA_SQL:
            d1_client.query(sql)
        return True
    except Exception as exc:
        _log.warning("fund_cn D1 ensure_schema soft-fail: %s", exc)
        return False


def seed_definitions() -> int:
    if not d1_client.configured():
        return 0
    try:
        ensure_schema()
        now = _now()
        statements: list[dict[str, Any]] = []
        for item in FACTOR_DEFINITIONS:
            statements.append(
                {
                    "sql": """
INSERT INTO fund_cn_factor_definitions(
  factor_id, factor_name, display_name, category, kind, formula,
  mvp, enabled, information_policy, raw_ok, compute_ok, pit_ok,
  factor_version, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(factor_id) DO UPDATE SET
  display_name=excluded.display_name,
  category=excluded.category,
  kind=excluded.kind,
  formula=excluded.formula,
  mvp=excluded.mvp,
  enabled=excluded.enabled,
  information_policy=excluded.information_policy,
  raw_ok=excluded.raw_ok,
  compute_ok=excluded.compute_ok,
  pit_ok=excluded.pit_ok,
  factor_version=excluded.factor_version,
  updated_at=excluded.updated_at
""".strip(),
                    "params": [
                        item.factor_id,
                        item.factor_id,
                        item.display_name,
                        item.category,
                        item.kind,
                        item.formula,
                        1 if item.mvp else 0,
                        1 if item.enabled else 0,
                        item.information_policy,
                        item.raw_ok,
                        item.compute_ok,
                        item.pit_ok,
                        FACTOR_VERSION,
                        now,
                    ],
                }
            )
        # batch in chunks
        for i in range(0, len(statements), 50):
            d1_client.batch(statements[i : i + 50])
        return len(statements)
    except Exception as exc:
        _log.warning("fund_cn seed_definitions soft-fail: %s", exc)
        return 0


def create_job(job_type: str, *, source_version: str = "") -> str | None:
    job_id = str(uuid.uuid4())
    if not d1_client.configured():
        return job_id
    try:
        ensure_schema()
        now = _now()
        d1_client.query(
            """
INSERT INTO fund_cn_factor_jobs(
  job_id, job_type, factor_version, status, source_version,
  rows_processed, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, 0, ?, ?)
""".strip(),
            [job_id, job_type, FACTOR_VERSION, "running", source_version, now, now],
        )
        return job_id
    except Exception as exc:
        _log.warning("fund_cn create_job soft-fail: %s", exc)
        return job_id


def finish_job(
    job_id: str | None,
    *,
    status: str = "done",
    rows_processed: int = 0,
    error_message: str = "",
) -> None:
    if not job_id or not d1_client.configured():
        return
    try:
        d1_client.query(
            """
UPDATE fund_cn_factor_jobs
SET status=?, rows_processed=?, error_message=?, updated_at=?
WHERE job_id=?
""".strip(),
            [status, rows_processed, error_message, _now(), job_id],
        )
    except Exception as exc:
        _log.warning("fund_cn finish_job soft-fail: %s", exc)


def upsert_period_status(
    period_key: str,
    job_type: str,
    *,
    source_version: str,
    status: str,
    error_message: str = "",
) -> None:
    if not d1_client.configured():
        return
    try:
        ensure_schema()
        d1_client.query(
            """
INSERT INTO fund_cn_period_status(
  period_key, job_type, factor_version, source_version, status, error_message, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(period_key, job_type, factor_version) DO UPDATE SET
  source_version=excluded.source_version,
  status=excluded.status,
  error_message=excluded.error_message,
  updated_at=excluded.updated_at
""".strip(),
            [
                period_key,
                job_type,
                FACTOR_VERSION,
                source_version,
                status,
                error_message,
                _now(),
            ],
        )
    except Exception as exc:
        _log.warning("fund_cn period_status soft-fail: %s", exc)


def register_dataset(storage_uri: str, *, row_count: int = 0, status: str = "ACTIVE") -> None:
    if not d1_client.configured():
        return
    try:
        ensure_schema()
        dataset_id = f"fund_cn_{FACTOR_SET}_{schema_hash()}"
        d1_client.query(
            """
INSERT INTO fund_cn_factor_datasets(
  dataset_id, factor_set, factor_version, storage_uri, schema_hash, row_count, status, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(dataset_id) DO UPDATE SET
  storage_uri=excluded.storage_uri,
  schema_hash=excluded.schema_hash,
  row_count=excluded.row_count,
  status=excluded.status
""".strip(),
            [
                dataset_id,
                FACTOR_SET,
                FACTOR_VERSION,
                storage_uri,
                schema_hash(),
                row_count,
                status,
                _now(),
            ],
        )
    except Exception as exc:
        _log.warning("fund_cn register_dataset soft-fail: %s", exc)
