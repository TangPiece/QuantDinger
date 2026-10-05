"""研究数据测试夹具：本地 CanonicalStore + LocalJsonRegistry。"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pyarrow as pa
import pytest

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.contracts import DatasetDefinition, FeatureDefinition, PricePolicy
from app.services.research_data.data_query import DataQuery
from app.services.research_data.registry import LocalJsonRegistry
from app.services.research_data.writer import (
    write_market_daily,
    write_pit_fundamental,
    write_snapshot_manifest,
    write_universe_snapshot,
)


@pytest.fixture
def research_env(tmp_path):
    store = LocalCanonicalStore(root=tmp_path / "canonical")
    registry = LocalJsonRegistry(root=tmp_path / "registry")
    return store, registry, DataQuery(store, registry)


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


@pytest.fixture
def seeded_research(research_env):
    """预置 market / pit / universe 与 dataset。"""
    store, registry, query = research_env
    market = pa.table(
        {
            "instrument_key": ["CNStock:000001", "CNStock:000002"],
            "trading_date": [date(2024, 5, 1), date(2024, 5, 1)],
            "open": [10.0, 20.0],
            "high": [11.0, 21.0],
            "low": [9.0, 19.0],
            "close": [10.5, 20.5],
            "volume": [1000.0, 2000.0],
            "amount": [10500.0, 41000.0],
            "vwap": [10.5, 20.5],
            "data_version": ["v1", "v1"],
        }
    )
    m = write_market_daily(
        store, market, exchange="CN", year=2024, month=5, registry=registry, version="2024.05"
    )
    pit = pa.table(
        {
            "instrument_key": ["CNStock:000001", "CNStock:000001", "CNStock:000001"],
            "metric_code": ["ROE", "ROE", "ROE"],
            "report_period_start": [date(2024, 1, 1)] * 3,
            "report_period_end": [date(2024, 3, 31)] * 3,
            "fiscal_year": [2024, 2024, 2024],
            "fiscal_quarter": [1, 1, 1],
            "publish_time": [_ts("2024-04-20T15:00:00"), _ts("2024-04-25T15:00:00"), _ts("2024-08-01T15:00:00")],
            "available_time": [_ts("2024-04-20T15:00:00"), _ts("2024-04-25T15:00:00"), _ts("2024-08-01T15:00:00")],
            "value": [10.1, 10.4, 10.7],
            "unit": ["pct", "pct", "pct"],
            "currency": ["CNY", "CNY", "CNY"],
            "revision": [0, 1, 2],
            "is_restatement": [False, True, True],
            "source": ["test", "test", "test"],
            "source_record_id": ["a", "b", "c"],
            "data_version": ["v1", "v1", "v1"],
        }
    )
    p = write_pit_fundamental(
        store, pit, exchange="CN", year=2024, registry=registry, version="2024.pit"
    )
    snap_id = "snap_test_001"
    univ = pa.table(
        {
            "universe_code": pa.array(["CSI300", "CSI300"]),
            "universe_version": pa.array(["2024.05", "2024.05"]),
            "instrument_key": pa.array(["CNStock:000001", "CNStock:999999"]),
            "valid_from": pa.array([date(2020, 1, 1), date(2020, 1, 1)], type=pa.date32()),
            "valid_to": pa.array([None, date(2023, 12, 31)], type=pa.date32()),
            "weight": pa.array([0.01, 0.01], type=pa.float64()),
            "member_rank": pa.array([1, 2], type=pa.int32()),
            "source_version": pa.array(["t", "t"]),
            "snapshot_id": pa.array([snap_id, snap_id]),
        }
    )
    u = write_universe_snapshot(
        store,
        univ,
        universe_code="CSI300",
        universe_version="2024.05",
        registry=registry,
    )
    items = [
        {
            "dataset_code": "market_daily",
            "version": "2024.05",
            "path": m["key"],
            "checksum": m["checksum"],
            "data_version_id": m.get("data_version_id"),
        },
        {
            "dataset_code": "pit_fundamental",
            "version": "2024.pit",
            "path": p["key"],
            "checksum": p["checksum"],
            "data_version_id": p.get("data_version_id"),
        },
        {
            "dataset_code": "universe_CSI300",
            "version": "2024.05",
            "path": u["key"],
            "checksum": u["checksum"],
            "r2_uri": u["key"],
            "data_version_id": u.get("data_version_id"),
        },
    ]
    write_snapshot_manifest(
        store, snapshot_id=snap_id, items=items, name="test", registry=registry
    )
    definition = DatasetDefinition(
        code="CSI300_DAILY",
        version="1.0.0",
        name="CSI300 Daily",
        frequency="1d",
        universe_code="CSI300",
        universe_version="2024.05",
        snapshot_id=snap_id,
        schema_version="market_bar_daily@1",
        features=["close"],
        price_policy=PricePolicy(adjustment="none"),
    )
    registry.upsert_dataset(definition)
    registry.upsert_feature(
        FeatureDefinition(
            code="CLOSE",
            version="1",
            name="Close",
            expression="close",
            backend="computed",
            definition={"source_column": "close"},
        )
    )
    return {
        "store": store,
        "registry": registry,
        "query": query,
        "snapshot_id": snap_id,
        "dataset_ref": "CSI300_DAILY@1.0.0",
    }
