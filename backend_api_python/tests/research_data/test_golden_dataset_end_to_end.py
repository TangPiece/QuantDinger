"""本地 fixture Golden：dataset(cn_stock_daily@v1) + market(...)。"""

from __future__ import annotations

from datetime import date

from app.services.research_data.contracts import PricePolicy
from app.services.research_data.data_query import DataQuery
from app.services.research_data.ingest.build_golden import (
    GOLDEN_DATASET_REF,
    build_golden_dataset,
)


def test_golden_dataset_end_to_end(tmp_path):
    from app.services.research_data.canonical_store import LocalCanonicalStore
    from app.services.research_data.registry import LocalJsonRegistry

    store = LocalCanonicalStore(root=tmp_path / "canonical")
    registry = LocalJsonRegistry(root=tmp_path / "registry")

    result = build_golden_dataset(
        store,
        registry,
        instrument_keys=["CNStock:000001", "CNStock:000002"],
        start=date(2024, 1, 1),
        end=date(2024, 3, 31),
        use_fixture=True,
        status="validated",
    )
    assert result["dataset_ref"] == GOLDEN_DATASET_REF
    assert result["status"] == "validated"
    assert result["dataset_hash"] == result["expected_hash"]
    assert result["dataset_hash"]
    assert result["r2_paths"]

    query = DataQuery(store, registry)
    handle = query.dataset(GOLDEN_DATASET_REF)
    assert handle.definition.code == "cn_stock_daily"
    assert handle.definition.version == "v1"
    assert handle.definition.snapshot_id == result["snapshot_id"]
    assert handle.dataset_hash == result["dataset_hash"]

    # Registry 旁路 status
    raw = registry._read()["datasets"][GOLDEN_DATASET_REF]
    assert raw.get("_registry_status") == "validated"

    raw_mkt = query.market(
        ["CNStock:000001"],
        date(2024, 1, 1),
        date(2024, 3, 31),
        price_policy=PricePolicy(adjustment="none"),
    )
    post_mkt = query.market(
        ["CNStock:000001"],
        date(2024, 1, 1),
        date(2024, 3, 31),
        price_policy=PricePolicy(adjustment="post"),
    )
    assert len(raw_mkt) >= 1
    assert len(post_mkt) == len(raw_mkt)
    # fixture CA effective 2024-06-01：2024Q1 全部应被后复权放大
    assert float(post_mkt.iloc[0]["close"]) != float(raw_mkt.iloc[0]["close"])

    members = query.universe(
        result["universe_code"],
        date(2024, 2, 1),
        snapshot_id=result["snapshot_id"],
        universe_version=result["universe_version"],
    )
    assert "CNStock:000001" in members
