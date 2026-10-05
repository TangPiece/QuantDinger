"""Canonical Parquet 写入 + data_version / snapshot 登记。"""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any, Optional

import pyarrow as pa
import pyarrow.parquet as pq

from . import paths, schemas
from .canonical_store import CanonicalStore
from .registry import ResearchRegistry


def table_checksum(table: pa.Table) -> str:
    """对 parquet 字节做 sha256。"""
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    return hashlib.sha256(buf.getvalue()).hexdigest()


def encode_parquet(table: pa.Table) -> bytes:
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    return buf.getvalue()


def put_parquet(
    store: CanonicalStore,
    key: str,
    table: pa.Table,
    *,
    expected_schema: pa.Schema,
    required_columns: list[str] | None = None,
) -> str:
    """校验 schema 后写入，返回 sha256 checksum。"""
    schemas.validate_table(table, expected_schema, required=required_columns)
    data = encode_parquet(table)
    store.put_bytes(key, data)
    return hashlib.sha256(data).hexdigest()


def write_market_daily(
    store: CanonicalStore,
    table: pa.Table,
    *,
    exchange: str,
    year: int,
    month: int,
    registry: ResearchRegistry | None = None,
    dataset_code: str = "market_daily",
    version: str,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """写入日线 Canonical 并可选登记 data_version。"""
    key = paths.market_daily_key(exchange=exchange, year=year, month=month, part=part)
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.market_bar_daily_schema(),
        required_columns=["instrument_key", "trading_date", "open", "high", "low", "close"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_MARKET,
        "row_count": table.num_rows,
    }
    if registry is not None:
        dv_id = registry.upsert_data_version(
            dataset_code=dataset_code,
            version=version,
            schema_version=schemas.SCHEMA_VERSION_MARKET,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
        result["data_version_id"] = dv_id
    return result


def write_pit_fundamental(
    store: CanonicalStore,
    table: pa.Table,
    *,
    exchange: str,
    year: int,
    registry: ResearchRegistry | None = None,
    dataset_code: str = "pit_fundamental",
    version: str,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    key = paths.pit_fundamental_key(exchange=exchange, year=year, part=part)
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.pit_fundamental_schema(),
        required_columns=[
            "instrument_key",
            "metric_code",
            "available_time",
            "value",
            "revision",
        ],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_PIT,
        "row_count": table.num_rows,
    }
    if registry is not None:
        dv_id = registry.upsert_data_version(
            dataset_code=dataset_code,
            version=version,
            schema_version=schemas.SCHEMA_VERSION_PIT,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
        result["data_version_id"] = dv_id
    return result


def write_universe_snapshot(
    store: CanonicalStore,
    table: pa.Table,
    *,
    universe_code: str,
    universe_version: str,
    registry: ResearchRegistry | None = None,
    dataset_code: str | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    key = paths.universe_snapshot_key(
        universe_code=universe_code,
        universe_version=universe_version,
        part=part,
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.universe_membership_schema(),
        required_columns=[
            "universe_code",
            "universe_version",
            "instrument_key",
            "valid_from",
            "snapshot_id",
        ],
    )
    uri = paths.r2_uri(key)
    code = dataset_code or f"universe_{universe_code}"
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_UNIVERSE,
        "row_count": table.num_rows,
    }
    if registry is not None:
        dv_id = registry.upsert_data_version(
            dataset_code=code,
            version=universe_version,
            schema_version=schemas.SCHEMA_VERSION_UNIVERSE,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
        result["data_version_id"] = dv_id
    return result


def write_factor_long(
    store: CanonicalStore,
    table: pa.Table,
    *,
    factor_set: str,
    year: int,
    month: int,
    registry: ResearchRegistry | None = None,
    version: str,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    key = paths.factor_daily_key(factor_set=factor_set, year=year, month=month, part=part)
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.factor_daily_long_schema(),
        required_columns=["instrument_key", "trading_date", "factor_code", "value"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_FACTOR_LONG,
        "row_count": table.num_rows,
    }
    if registry is not None:
        dv_id = registry.upsert_data_version(
            dataset_code=f"factor_set_{factor_set}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_FACTOR_LONG,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
        result["data_version_id"] = dv_id
    return result


def write_snapshot_manifest(
    store: CanonicalStore,
    *,
    snapshot_id: str,
    items: list[dict[str, Any]],
    name: str = "",
    registry: Optional[ResearchRegistry] = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """写 qd/snapshot/{id}/manifest.json 并登记 Registry。"""
    payload = {
        "snapshot_id": snapshot_id,
        "name": name,
        "schema_version": "snapshot_manifest@1",
        "items": items,
        "metadata": metadata or {},
    }
    key = paths.snapshot_manifest_key(snapshot_id)
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    store.put_bytes(key, data)
    if registry is not None:
        registry.create_snapshot(
            snapshot_id=snapshot_id,
            name=name or snapshot_id,
            items=items,
            metadata=metadata,
        )
    return key


def read_parquet_table(store: CanonicalStore, key: str) -> pa.Table:
    """从 CanonicalStore 读取 parquet。"""
    data = store.get_bytes(key)
    return pq.read_table(io.BytesIO(data))
