"""Canonical Parquet Arrow schema 与校验（docs/data/phase1/04_parquet_schemas.md）。"""

from __future__ import annotations

from typing import Iterable

import pyarrow as pa

SCHEMA_VERSION_MARKET = "market_bar_daily@1"
SCHEMA_VERSION_PIT = "pit_fundamental@1"
SCHEMA_VERSION_UNIVERSE = "universe_membership_snapshot@1"
SCHEMA_VERSION_CORPORATE_ACTION = "corporate_action@1"
SCHEMA_VERSION_TRADING_STATUS = "trading_status@1"
SCHEMA_VERSION_FACTOR_LONG = "factor_daily_long@1"
SCHEMA_VERSION_FACTOR_WIDE = "factor_daily_wide@1"
SCHEMA_VERSION_EVALUATION = "evaluation_panel@1"


def market_bar_daily_schema() -> pa.Schema:
    return pa.schema(
        [
            ("instrument_key", pa.string()),
            ("trading_date", pa.date32()),
            ("open", pa.float64()),
            ("high", pa.float64()),
            ("low", pa.float64()),
            ("close", pa.float64()),
            ("volume", pa.float64()),
            ("amount", pa.float64()),
            ("vwap", pa.float64()),
            ("data_version", pa.string()),
        ]
    )


def pit_fundamental_schema() -> pa.Schema:
    return pa.schema(
        [
            ("instrument_key", pa.string()),
            ("metric_code", pa.string()),
            ("report_period_start", pa.date32()),
            ("report_period_end", pa.date32()),
            ("fiscal_year", pa.int32()),
            ("fiscal_quarter", pa.int32()),
            ("publish_time", pa.timestamp("us", tz="UTC")),
            ("available_time", pa.timestamp("us", tz="UTC")),
            ("value", pa.float64()),
            ("unit", pa.string()),
            ("currency", pa.string()),
            ("revision", pa.int32()),
            ("is_restatement", pa.bool_()),
            ("source", pa.string()),
            ("source_record_id", pa.string()),
            ("data_version", pa.string()),
        ]
    )


def universe_membership_schema() -> pa.Schema:
    return pa.schema(
        [
            ("universe_code", pa.string()),
            ("universe_version", pa.string()),
            ("instrument_key", pa.string()),
            ("valid_from", pa.date32()),
            ("valid_to", pa.date32()),
            ("weight", pa.float64()),
            ("member_rank", pa.int32()),
            ("source_version", pa.string()),
            ("snapshot_id", pa.string()),
        ]
    )


def corporate_action_schema() -> pa.Schema:
    return pa.schema(
        [
            ("instrument_key", pa.string()),
            ("effective_date", pa.date32()),
            ("action_type", pa.string()),
            ("cash_dividend", pa.float64()),
            ("split_ratio", pa.float64()),
            ("rights_ratio", pa.float64()),
            ("rights_price", pa.float64()),
            ("currency", pa.string()),
            ("source", pa.string()),
            ("source_version", pa.string()),
            ("data_version", pa.string()),
        ]
    )


def trading_status_schema() -> pa.Schema:
    return pa.schema(
        [
            ("instrument_key", pa.string()),
            ("trading_date", pa.date32()),
            ("status", pa.string()),
            ("is_suspended", pa.bool_()),
            ("is_limit_up", pa.bool_()),
            ("is_limit_down", pa.bool_()),
            ("upper_limit", pa.float64()),
            ("lower_limit", pa.float64()),
            ("data_version", pa.string()),
        ]
    )


def factor_daily_long_schema() -> pa.Schema:
    return pa.schema(
        [
            ("instrument_key", pa.string()),
            ("trading_date", pa.date32()),
            ("factor_code", pa.string()),
            ("factor_version", pa.string()),
            ("value", pa.float64()),
            ("data_version", pa.string()),
        ]
    )


def factor_daily_wide_schema(*, factor_columns: Iterable[str] | None = None) -> pa.Schema:
    """Wide 因子面板：固定键列 + 动态因子列（4A 定义；4B 填充）。"""
    fields = [
        ("instrument_key", pa.string()),
        ("trading_date", pa.date32()),
        ("data_version", pa.string()),
    ]
    for col in factor_columns or ():
        fields.append((str(col), pa.float64()))
    return pa.schema(fields)


def evaluation_panel_schema(*, horizons: Iterable[int] | None = None) -> pa.Schema:
    """评价面板：因子 + 多 horizon 远期收益 + sample_status。"""
    fields = [
        ("instrument_key", pa.string()),
        ("factor_date", pa.date32()),
        ("factor_value", pa.float64()),
        ("entry_date", pa.date32()),
        ("exit_date", pa.date32()),
        ("universe_code", pa.string()),
        ("snapshot_id", pa.string()),
        ("sample_status", pa.string()),
        ("mode", pa.string()),
        ("data_version", pa.string()),
    ]
    for h in horizons or ():
        fields.append((f"forward_return_{int(h)}d", pa.float64()))
    return pa.schema(fields)


class SchemaValidationError(ValueError):
    """Parquet 列集合与约定 schema 不一致。"""


def validate_table(table: pa.Table, expected: pa.Schema, *, required: Iterable[str] | None = None) -> None:
    """校验表至少包含 required 列且类型与 expected 兼容。"""
    names = set(table.schema.names)
    need = list(required) if required is not None else list(expected.names)
    missing = [n for n in need if n not in names]
    if missing:
        raise SchemaValidationError(f"missing columns: {missing}")
    for field in expected:
        if field.name not in names:
            continue
        actual = table.schema.field(field.name).type
        if not _types_compatible(actual, field.type):
            raise SchemaValidationError(
                f"column {field.name}: expected {field.type}, got {actual}"
            )


def _types_compatible(actual: pa.DataType, expected: pa.DataType) -> bool:
    if actual.equals(expected):
        return True
    # 允许无 tz 的 timestamp 写入时再规范；读侧宽松一点
    if pa.types.is_timestamp(actual) and pa.types.is_timestamp(expected):
        return True
    # Python/pandas 常把小整数推断为 int64
    if pa.types.is_integer(actual) and pa.types.is_integer(expected):
        return True
    if pa.types.is_floating(actual) and pa.types.is_floating(expected):
        return True
    if pa.types.is_null(actual):
        return True
    return False
