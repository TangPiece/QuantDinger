"""Canonical Parquet 写入 + data_version / snapshot 登记。"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import date
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


def write_corporate_action(
    store: CanonicalStore,
    table: pa.Table,
    *,
    exchange: str,
    year: int,
    registry: ResearchRegistry | None = None,
    dataset_code: str = "corporate_action",
    version: str,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """写入公司行为 / 复权因子 Canonical。"""
    key = paths.corporate_action_key(exchange=exchange, year=year, part=part)
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.corporate_action_schema(),
        required_columns=["instrument_key", "effective_date", "action_type"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_CORPORATE_ACTION,
        "row_count": table.num_rows,
    }
    if registry is not None:
        dv_id = registry.upsert_data_version(
            dataset_code=dataset_code,
            version=version,
            schema_version=schemas.SCHEMA_VERSION_CORPORATE_ACTION,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
        result["data_version_id"] = dv_id
    return result


def write_trading_status(
    store: CanonicalStore,
    table: pa.Table,
    *,
    exchange: str,
    year: int,
    month: int,
    registry: ResearchRegistry | None = None,
    dataset_code: str = "trading_status",
    version: str,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """写入停牌/涨跌停 Canonical；允许空表（空分区占位）。"""
    key = paths.trading_status_key(exchange=exchange, year=year, month=month, part=part)
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.trading_status_schema(),
        required_columns=["instrument_key", "trading_date", "status"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_TRADING_STATUS,
        "row_count": table.num_rows,
    }
    if registry is not None:
        dv_id = registry.upsert_data_version(
            dataset_code=dataset_code,
            version=version,
            schema_version=schemas.SCHEMA_VERSION_TRADING_STATUS,
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


def write_factor_wide(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    factor_set: str,
    year: int,
    month: int,
    version: str,
    factor_columns: list[str],
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """写入 Wide 因子面板（Phase 4B）。"""
    # 规范化日期
    norm: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        td = item.get("trading_date")
        if isinstance(td, str):
            item["trading_date"] = date.fromisoformat(td[:10])
        elif hasattr(td, "date") and not isinstance(td, date):
            item["trading_date"] = td.date()
        item.setdefault("data_version", version)
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    expected = schemas.factor_daily_wide_schema(factor_columns=factor_columns)
    key = paths.factor_daily_key(factor_set=factor_set, year=year, month=month, part=part)
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=expected,
        required_columns=["instrument_key", "trading_date"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_FACTOR_WIDE,
        "row_count": table.num_rows,
    }
    if registry is not None:
        dv_id = registry.upsert_data_version(
            dataset_code=f"factor_set_{factor_set}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_FACTOR_WIDE,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
        result["data_version_id"] = dv_id
    return result


def write_evaluation_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    evaluation_hash: str,
    year: int,
    month: int,
    horizons: list[int],
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """写入评价面板分区 parquet（Phase 4C）。"""
    norm: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        for col in ("factor_date", "entry_date", "exit_date"):
            v = item.get(col)
            if v is None:
                continue
            if isinstance(v, str):
                item[col] = date.fromisoformat(v[:10])
            elif hasattr(v, "date") and not isinstance(v, date):
                item[col] = v.date()
        item.setdefault("data_version", version)
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    expected = schemas.evaluation_panel_schema(horizons=horizons)
    key = paths.evaluation_factor_key(
        evaluation_hash=evaluation_hash, year=year, month=month, part=part
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=expected,
        required_columns=[
            "instrument_key",
            "factor_date",
            "sample_status",
        ],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_EVALUATION,
        "row_count": table.num_rows,
    }
    if registry is not None:
        dv_id = registry.upsert_data_version(
            dataset_code=f"evaluation_{evaluation_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_EVALUATION,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
        result["data_version_id"] = dv_id
    return result


def write_metric_ic_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    metric_hash: str,
    year: int,
    month: int,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """写入 IC 日度时间序列分区（Phase 4D）。"""
    norm: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        ed = item.get("evaluation_date")
        if isinstance(ed, str):
            item["evaluation_date"] = date.fromisoformat(ed[:10])
        elif hasattr(ed, "date") and not isinstance(ed, date):
            item["evaluation_date"] = ed.date()
        item.setdefault("data_version", version)
        # None → NaN for float columns so Arrow accepts
        for col in ("ic", "rank_ic"):
            if item.get(col) is None:
                item[col] = float("nan")
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.evaluation_metrics_ic_key(
        metric_hash=metric_hash, year=year, month=month, part=part
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.metric_ic_daily_schema(),
        required_columns=["evaluation_date", "horizon", "sample_count", "valid"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_METRIC_IC,
        "row_count": table.num_rows,
    }
    if registry is not None:
        dv_id = registry.upsert_data_version(
            dataset_code=f"metric_ic_{metric_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_METRIC_IC,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
        result["data_version_id"] = dv_id
    return result


def _norm_eval_date(item: dict[str, Any]) -> dict[str, Any]:
    ed = item.get("evaluation_date")
    if isinstance(ed, str):
        item["evaluation_date"] = date.fromisoformat(ed[:10])
    elif hasattr(ed, "date") and not isinstance(ed, date):
        item["evaluation_date"] = ed.date()
    return item


def write_group_membership_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    group_evaluation_hash: str,
    year: int,
    month: int,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4E：分位成员分区。"""
    norm = []
    for r in rows:
        item = _norm_eval_date(dict(r))
        item.setdefault("data_version", version)
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.evaluation_groups_key(
        group_evaluation_hash=group_evaluation_hash,
        kind="group_membership",
        year=year,
        month=month,
        part=part,
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.group_membership_schema(),
        required_columns=["evaluation_date", "horizon", "instrument_key", "group"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_GROUP_MEMBERSHIP,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"group_mem_{group_evaluation_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_GROUP_MEMBERSHIP,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_group_return_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    group_evaluation_hash: str,
    year: int,
    month: int,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4E：分位收益分区。"""
    float_cols = (
        "group_return",
        "long_return",
        "short_return",
        "long_short_return",
        "estimated_cost",
        "net_long_short_return",
    )
    norm = []
    for r in rows:
        item = _norm_eval_date(dict(r))
        item.setdefault("data_version", version)
        for col in float_cols:
            if item.get(col) is None:
                item[col] = float("nan")
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.evaluation_groups_key(
        group_evaluation_hash=group_evaluation_hash,
        kind="group_returns",
        year=year,
        month=month,
        part=part,
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.group_return_daily_schema(),
        required_columns=["evaluation_date", "horizon", "group", "sample_count"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_GROUP_RETURN,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"group_ret_{group_evaluation_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_GROUP_RETURN,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_group_turnover_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    group_evaluation_hash: str,
    year: int,
    month: int,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4E：换手分区。"""
    norm = []
    for r in rows:
        item = _norm_eval_date(dict(r))
        item.setdefault("data_version", version)
        if item.get("turnover") is None:
            item["turnover"] = float("nan")
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.evaluation_groups_key(
        group_evaluation_hash=group_evaluation_hash,
        kind="turnover",
        year=year,
        month=month,
        part=part,
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.group_turnover_daily_schema(),
        required_columns=["evaluation_date", "horizon", "portfolio"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_GROUP_TURNOVER,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"group_to_{group_evaluation_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_GROUP_TURNOVER,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def _nan_floats(item: dict[str, Any], cols: tuple[str, ...]) -> dict[str, Any]:
    for col in cols:
        if item.get(col) is None:
            item[col] = float("nan")
    return item


def write_rolling_ic_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    stability_hash: str,
    year: int,
    month: int,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4F：滚动 IC 分区。"""
    float_cols = ("ic_mean", "rankic_mean", "ic_std", "ic_positive_ratio")
    norm = []
    for r in rows:
        item = _nan_floats(_norm_eval_date(dict(r)), float_cols)
        item.setdefault("data_version", version)
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.evaluation_stability_key(
        stability_hash=stability_hash,
        kind="rolling_ic",
        year=year,
        month=month,
        part=part,
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.rolling_ic_daily_schema(),
        required_columns=["evaluation_date", "horizon", "window", "sample_count"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_ROLLING_IC,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"stab_roll_{stability_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_ROLLING_IC,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_decay_curve_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    stability_hash: str,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4F：Decay 曲线（无年月分区）。"""
    float_cols = (
        "ic_mean",
        "rankic_mean",
        "long_return",
        "short_return",
        "long_short_return",
    )
    norm = []
    for r in rows:
        item = _nan_floats(dict(r), float_cols)
        item.setdefault("data_version", version)
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.evaluation_stability_key(
        stability_hash=stability_hash, kind="decay", part=part
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.decay_curve_schema(),
        required_columns=["horizon", "sample_count"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_DECAY,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"stab_decay_{stability_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_DECAY,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_group_stability_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    stability_hash: str,
    year: int,
    month: int,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4F：Group 稳定性分区。"""
    float_cols = ("mean_return", "std_return", "positive_ratio")
    norm = []
    for r in rows:
        item = _nan_floats(_norm_eval_date(dict(r)), float_cols)
        item.setdefault("data_version", version)
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.evaluation_stability_key(
        stability_hash=stability_hash,
        kind="group_stability",
        year=year,
        month=month,
        part=part,
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.group_stability_daily_schema(),
        required_columns=["evaluation_date", "horizon", "window", "portfolio"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_GROUP_STABILITY,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"stab_gst_{stability_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_GROUP_STABILITY,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_regime_metrics_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    stability_hash: str,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4F：Regime 指标（无年月分区）。"""
    float_cols = (
        "ic_mean",
        "rankic_mean",
        "long_short_return",
        "turnover",
        "net_return",
    )
    norm = []
    for r in rows:
        item = _nan_floats(dict(r), float_cols)
        item.setdefault("data_version", version)
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.evaluation_stability_key(
        stability_hash=stability_hash, kind="regime", part=part
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.regime_metrics_schema(),
        required_columns=["regime_type", "regime_value", "horizon"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_REGIME,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"stab_reg_{stability_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_REGIME,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_neutralized_factor_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    neutralization_hash: str,
    year: int,
    month: int,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4G：审计用 raw + neutralized 分区。"""
    norm = []
    for r in rows:
        item = _norm_eval_date_as_trading(dict(r))
        item.setdefault("data_version", version)
        item.setdefault("neutralization_hash", neutralization_hash)
        if item.get("neutralized_factor") is None:
            item["neutralized_factor"] = float("nan")
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.neutralized_factor_key(
        neutralization_hash=neutralization_hash,
        kind="factor",
        year=year,
        month=month,
        part=part,
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.neutralized_factor_daily_schema(),
        required_columns=["instrument_key", "trading_date", "raw_factor"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_NEUTRALIZED,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"neut_fac_{neutralization_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_NEUTRALIZED,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_exposure_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    neutralization_hash: str,
    year: int,
    month: int,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4G：暴露分区。"""
    from datetime import datetime, timezone

    norm = []
    for r in rows:
        item = _norm_eval_date_as_trading(dict(r))
        item.setdefault("data_version", version)
        at = item.get("available_time")
        if isinstance(at, str):
            item["available_time"] = datetime.fromisoformat(
                at.replace("Z", "+00:00")
            )
        elif at is None:
            item["available_time"] = datetime(1970, 1, 1, tzinfo=timezone.utc)
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.neutralized_factor_key(
        neutralization_hash=neutralization_hash,
        kind="exposure",
        year=year,
        month=month,
        part=part,
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.exposure_daily_schema(),
        required_columns=["instrument_key", "trading_date", "exposure_code"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_EXPOSURE,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"neut_exp_{neutralization_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_EXPOSURE,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_portfolio_position_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    portfolio_hash: str,
    year: int,
    month: int,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4I：TargetPosition 兼容持仓分区。"""
    from datetime import datetime, timezone

    norm = []
    for r in rows:
        item = dict(r)
        item.setdefault("data_version", version)
        ts = item.get("timestamp")
        if isinstance(ts, str):
            item["timestamp"] = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        elif ts is None:
            item["timestamp"] = datetime(1970, 1, 1, tzinfo=timezone.utc)
        if item.get("target_weight") is None:
            item["target_weight"] = float("nan")
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.factor_portfolio_key(
        portfolio_hash=portfolio_hash,
        kind="positions",
        year=year,
        month=month,
        part=part,
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.portfolio_position_schema(),
        required_columns=["instrument_key", "trading_date", "target_weight"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_PORT_POSITION,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"pf_pos_{portfolio_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_PORT_POSITION,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_portfolio_weight_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    portfolio_hash: str,
    year: int,
    month: int,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4I：权重审计分区。"""
    norm = []
    for r in rows:
        item = _norm_eval_date_as_trading(dict(r))
        item.setdefault("data_version", version)
        if item.get("weight") is None:
            item["weight"] = float("nan")
        if item.get("factor_value") is None:
            item["factor_value"] = float("nan")
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.factor_portfolio_key(
        portfolio_hash=portfolio_hash,
        kind="weights",
        year=year,
        month=month,
        part=part,
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.portfolio_weight_schema(),
        required_columns=["trading_date", "instrument_key", "weight"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_PORT_WEIGHT,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"pf_w_{portfolio_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_PORT_WEIGHT,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_portfolio_return_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    portfolio_hash: str,
    year: int,
    month: int,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4I：理论组合日收益。"""
    float_cols = (
        "portfolio_return",
        "long_return",
        "short_return",
        "long_short_return",
    )
    norm = []
    for r in rows:
        item = _norm_eval_date_as_trading(dict(r))
        item.setdefault("data_version", version)
        for col in float_cols:
            if item.get(col) is None:
                item[col] = float("nan")
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.factor_portfolio_key(
        portfolio_hash=portfolio_hash,
        kind="returns",
        year=year,
        month=month,
        part=part,
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.portfolio_return_daily_schema(),
        required_columns=["trading_date", "sample_count"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_PORT_RETURN,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"pf_ret_{portfolio_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_PORT_RETURN,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_portfolio_turnover_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    portfolio_hash: str,
    year: int,
    month: int,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4I：日换手。"""
    norm = []
    for r in rows:
        item = _norm_eval_date_as_trading(dict(r))
        item.setdefault("data_version", version)
        if item.get("turnover") is None:
            item["turnover"] = float("nan")
        item["rebalanced"] = bool(item.get("rebalanced"))
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.factor_portfolio_key(
        portfolio_hash=portfolio_hash,
        kind="turnover",
        year=year,
        month=month,
        part=part,
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.portfolio_turnover_daily_schema(),
        required_columns=["trading_date", "rebalanced"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_PORT_TURNOVER,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"pf_to_{portfolio_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_PORT_TURNOVER,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_composite_factor_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    combination_hash: str,
    year: int,
    month: int,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4H：审计用 composite（可含成员列）。"""
    norm = []
    for r in rows:
        item = _norm_eval_date_as_trading(dict(r))
        item.setdefault("data_version", version)
        item.setdefault("combination_hash", combination_hash)
        if item.get("composite") is None:
            item["composite"] = float("nan")
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.combined_factor_key(
        combination_hash=combination_hash,
        kind="composite",
        year=year,
        month=month,
        part=part,
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.composite_factor_daily_schema(),
        required_columns=["instrument_key", "trading_date", "composite"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_COMPOSITE,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"comb_fac_{combination_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_COMPOSITE,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_factor_corr_matrix_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    combination_hash: str,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4H：相关矩阵（无年月分区）。"""
    norm = []
    for r in rows:
        item = dict(r)
        item.setdefault("data_version", version)
        if item.get("corr") is None:
            item["corr"] = float("nan")
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.combined_factor_key(
        combination_hash=combination_hash, kind="correlation", part=part
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.factor_corr_matrix_schema(),
        required_columns=["factor_i", "factor_j", "corr"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_FACTOR_CORR,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"comb_corr_{combination_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_FACTOR_CORR,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_combination_weights_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    combination_hash: str,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4H：组合权重。"""
    norm = []
    for r in rows:
        item = dict(r)
        item.setdefault("data_version", version)
        if item.get("weight") is None:
            item["weight"] = float("nan")
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.combined_factor_key(
        combination_hash=combination_hash, kind="weights", part=part
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.combination_weights_schema(),
        required_columns=["factor_dataset_id", "weight"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_COMB_WEIGHTS,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"comb_w_{combination_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_COMB_WEIGHTS,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def write_neutralization_diagnostics_panel(
    store: CanonicalStore,
    rows: list[dict[str, Any]],
    *,
    neutralization_hash: str,
    version: str,
    registry: ResearchRegistry | None = None,
    part: str = "part-000.parquet",
) -> dict[str, Any]:
    """Phase 4G：诊断（无年月分区）。"""
    float_cols = (
        "correlation_before",
        "correlation_after",
        "spearman_before",
        "spearman_after",
        "r_squared",
    )
    norm = []
    for r in rows:
        item = _norm_eval_date_as_trading(dict(r))
        item.setdefault("data_version", version)
        for col in float_cols:
            if item.get(col) is None:
                item[col] = float("nan")
        norm.append(item)
    table = pa.Table.from_pylist(norm)
    key = paths.neutralized_factor_key(
        neutralization_hash=neutralization_hash, kind="diagnostics", part=part
    )
    checksum = put_parquet(
        store,
        key,
        table,
        expected_schema=schemas.neutralization_diagnostics_schema(),
        required_columns=["trading_date", "exposure_code", "sample_count"],
    )
    uri = paths.r2_uri(key)
    result: dict[str, Any] = {
        "key": key,
        "checksum": checksum,
        "r2_uri": uri,
        "schema_version": schemas.SCHEMA_VERSION_NEUT_DIAG,
        "row_count": table.num_rows,
    }
    if registry is not None:
        result["data_version_id"] = registry.upsert_data_version(
            dataset_code=f"neut_diag_{neutralization_hash[:16]}",
            version=version,
            schema_version=schemas.SCHEMA_VERSION_NEUT_DIAG,
            status="ACTIVE",
            checksum=checksum,
            r2_uri=uri,
            row_count=table.num_rows,
        )
    return result


def _norm_eval_date_as_trading(item: dict[str, Any]) -> dict[str, Any]:
    """统一 trading_date / evaluation_date 为 date。"""
    td = item.get("trading_date") or item.get("evaluation_date")
    if isinstance(td, str):
        item["trading_date"] = date.fromisoformat(td[:10])
    elif hasattr(td, "date") and not isinstance(td, date):
        item["trading_date"] = td.date()
    elif isinstance(td, date):
        item["trading_date"] = td
    item.pop("evaluation_date", None)
    return item


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
