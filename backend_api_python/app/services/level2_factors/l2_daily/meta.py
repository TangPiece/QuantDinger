"""D1 元数据：definitions / jobs / datasets / day_status。"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.level2_factors import d1_client

from .catalog import FACTOR_DEFINITIONS, FACTOR_VERSION

_log = logging.getLogger(__name__)

_SCHEMA_SQL = [
    """
CREATE TABLE IF NOT EXISTS l2_factor_definitions (
  factor_id TEXT PRIMARY KEY,
  factor_name TEXT NOT NULL,
  display_name TEXT,
  category TEXT NOT NULL,
  description TEXT,
  formula TEXT,
  input_fields TEXT,
  frequency TEXT NOT NULL DEFAULT 'day',
  factor_version INTEGER NOT NULL DEFAULT 1,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
""".strip(),
    """
CREATE TABLE IF NOT EXISTS l2_factor_jobs (
  job_id TEXT PRIMARY KEY,
  factor_group TEXT NOT NULL,
  factor_version INTEGER NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  status TEXT NOT NULL,
  rows_processed INTEGER DEFAULT 0,
  error_message TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
""".strip(),
    """
CREATE TABLE IF NOT EXISTS l2_factor_datasets (
  dataset_id TEXT PRIMARY KEY,
  factor_group TEXT NOT NULL,
  factor_version INTEGER NOT NULL,
  source_version TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  storage_uri TEXT NOT NULL,
  schema_hash TEXT NOT NULL,
  row_count INTEGER,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
)
""".strip(),
    """
CREATE TABLE IF NOT EXISTS l2_factor_day_status (
  trade_date TEXT NOT NULL,
  factor_group TEXT NOT NULL,
  factor_version INTEGER NOT NULL,
  source_version TEXT NOT NULL,
  status TEXT NOT NULL,
  symbol_ok INTEGER DEFAULT 0,
  symbol_fail INTEGER DEFAULT 0,
  schema_hash TEXT,
  error_message TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (trade_date, factor_group, factor_version)
)
""".strip(),
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_schema() -> None:
    """幂等建元数据表。D1 未配置时跳过。"""
    if not d1_client.configured():
        return
    for sql in _SCHEMA_SQL:
        d1_client.query(sql)


def seed_definitions(*, factor_version: int = FACTOR_VERSION) -> int:
    """幂等写入 100 条因子定义。返回写入语句涉及的条数。"""
    if not d1_client.configured():
        return 0
    ensure_schema()
    now = _now()
    statements: list[dict[str, Any]] = []
    for item in FACTOR_DEFINITIONS:
        statements.append(
            {
                "sql": """
INSERT INTO l2_factor_definitions (
  factor_id, factor_name, display_name, category, description, formula,
  input_fields, frequency, factor_version, enabled, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, 'day', ?, 1, ?, ?)
ON CONFLICT(factor_id) DO UPDATE SET
  factor_name=excluded.factor_name,
  display_name=excluded.display_name,
  category=excluded.category,
  description=excluded.description,
  formula=excluded.formula,
  input_fields=excluded.input_fields,
  factor_version=excluded.factor_version,
  enabled=excluded.enabled,
  updated_at=excluded.updated_at
""".strip(),
                "params": [
                    item.factor_id,
                    item.factor_name,
                    item.display_name,
                    item.category,
                    item.description,
                    item.formula,
                    item.input_fields,
                    factor_version,
                    now,
                    now,
                ],
            }
        )
        if len(statements) >= d1_client.MAX_BATCH_STATEMENTS:
            d1_client.batch(statements)
            statements = []
    if statements:
        d1_client.batch(statements)
    return len(FACTOR_DEFINITIONS)


def get_day_status(
    trade_date: str,
    factor_group: str,
    *,
    factor_version: int = FACTOR_VERSION,
) -> dict[str, Any] | None:
    if not d1_client.configured():
        return None
    rows = d1_client.query(
        """
SELECT * FROM l2_factor_day_status
WHERE trade_date=? AND factor_group=? AND factor_version=?
LIMIT 1
""".strip(),
        [str(trade_date), str(factor_group), int(factor_version)],
    )
    return rows[0] if rows else None


def upsert_day_status(
    *,
    trade_date: str,
    factor_group: str,
    source_version: str,
    status: str,
    symbol_ok: int = 0,
    symbol_fail: int = 0,
    schema_hash: str = "",
    error_message: str | None = None,
    factor_version: int = FACTOR_VERSION,
) -> None:
    if not d1_client.configured():
        return
    ensure_schema()
    now = _now()
    d1_client.query(
        """
INSERT INTO l2_factor_day_status (
  trade_date, factor_group, factor_version, source_version, status,
  symbol_ok, symbol_fail, schema_hash, error_message, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(trade_date, factor_group, factor_version) DO UPDATE SET
  source_version=excluded.source_version,
  status=excluded.status,
  symbol_ok=excluded.symbol_ok,
  symbol_fail=excluded.symbol_fail,
  schema_hash=excluded.schema_hash,
  error_message=excluded.error_message,
  updated_at=excluded.updated_at
""".strip(),
        [
            str(trade_date),
            str(factor_group),
            int(factor_version),
            str(source_version),
            str(status),
            int(symbol_ok),
            int(symbol_fail),
            str(schema_hash or ""),
            error_message,
            now,
        ],
    )


def create_job(
    *,
    factor_group: str,
    start_date: str,
    end_date: str,
    factor_version: int = FACTOR_VERSION,
) -> str:
    job_id = uuid.uuid4().hex
    if not d1_client.configured():
        return job_id
    ensure_schema()
    now = _now()
    d1_client.query(
        """
INSERT INTO l2_factor_jobs (
  job_id, factor_group, factor_version, start_date, end_date,
  status, rows_processed, error_message, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, 'running', 0, NULL, ?, ?)
""".strip(),
        [job_id, factor_group, int(factor_version), start_date, end_date, now, now],
    )
    return job_id


def finish_job(
    job_id: str,
    *,
    status: str,
    rows_processed: int = 0,
    error_message: str | None = None,
) -> None:
    if not d1_client.configured():
        return
    d1_client.query(
        """
UPDATE l2_factor_jobs
SET status=?, rows_processed=?, error_message=?, updated_at=?
WHERE job_id=?
""".strip(),
        [status, int(rows_processed), error_message, _now(), job_id],
    )


def upsert_dataset(
    *,
    dataset_id: str,
    factor_group: str,
    source_version: str,
    start_date: str,
    end_date: str,
    storage_uri: str,
    schema_hash: str,
    row_count: int | None,
    status: str = "ready",
    factor_version: int = FACTOR_VERSION,
) -> None:
    if not d1_client.configured():
        return
    ensure_schema()
    # 先删再插，避免同日多版本残留（dataset_id 由调用方稳定生成）。
    d1_client.query("DELETE FROM l2_factor_datasets WHERE dataset_id=?", [dataset_id])
    d1_client.query(
        """
INSERT INTO l2_factor_datasets (
  dataset_id, factor_group, factor_version, source_version,
  start_date, end_date, storage_uri, schema_hash, row_count, status, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""".strip(),
        [
            dataset_id,
            factor_group,
            int(factor_version),
            source_version,
            start_date,
            end_date,
            storage_uri,
            schema_hash,
            row_count,
            status,
            _now(),
        ],
    )


def dataset_id_for(trade_date: str, factor_group: str, factor_version: int = FACTOR_VERSION) -> str:
    return f"l2_daily_{factor_group}_v{factor_version}_{trade_date}"
