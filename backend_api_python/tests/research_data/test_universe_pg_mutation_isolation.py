"""读 snapshot 后 PG members 变化，再读 snapshot 不变。"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pyarrow as pa

from app.services.research_data.contracts import DatasetDefinition, PricePolicy
from app.services.research_data.data_query import DataQuery
from app.services.research_data.writer import write_snapshot_manifest, write_universe_snapshot


def test_universe_snapshot_immune_to_pg_mutation(research_env, monkeypatch):
    store, registry, query = research_env
    snap_id = "snap_pg_iso"
    univ = pa.table(
        {
            "universe_code": pa.array(["CSI300", "CSI300"]),
            "universe_version": pa.array(["iso.1", "iso.1"]),
            "instrument_key": pa.array(["CNStock:000001", "CNStock:000002"]),
            "valid_from": pa.array([date(2020, 1, 1), date(2020, 1, 1)], type=pa.date32()),
            "valid_to": pa.array([None, None], type=pa.date32()),
            "weight": pa.array([0.5, 0.5], type=pa.float64()),
            "member_rank": pa.array([1, 2], type=pa.int32()),
            "source_version": pa.array(["pg", "pg"]),
            "snapshot_id": pa.array([snap_id, snap_id]),
        }
    )
    u = write_universe_snapshot(
        store,
        univ,
        universe_code="CSI300",
        universe_version="iso.1",
        registry=registry,
    )
    write_snapshot_manifest(
        store,
        snapshot_id=snap_id,
        items=[
            {
                "dataset_code": "universe_CSI300",
                "version": "iso.1",
                "path": u["key"],
                "checksum": u["checksum"],
                "r2_uri": u["key"],
            }
        ],
        name="iso",
        registry=registry,
    )
    registry.upsert_dataset(
        DatasetDefinition(
            code="iso_ds",
            version="1",
            name="iso",
            frequency="1d",
            universe_code="CSI300",
            universe_version="iso.1",
            snapshot_id=snap_id,
            schema_version="market_bar_daily@1",
            features=["close"],
            price_policy=PricePolicy(),
        )
    )

    before = query.universe(
        "CSI300",
        datetime(2024, 6, 1, tzinfo=timezone.utc),
        snapshot_id=snap_id,
        universe_version="iso.1",
    )
    assert before == ["CNStock:000001", "CNStock:000002"]

    # 模拟 PG 成分变更：monkeypatch UniverseService；DataQuery 仍只读 snapshot
    class FakeUniverseService:
        def list_universes(self, *_a, **_k):
            return [{"id": 1, "code": "CSI300"}]

        def get_members(self, *_a, **_k):
            return [{"instrument_key": "CNStock:999999", "symbol": "999999"}]

    monkeypatch.setattr(
        "app.services.universe.UniverseService",
        FakeUniverseService,
        raising=True,
    )

    after = query.universe(
        "CSI300",
        datetime(2024, 6, 1, tzinfo=timezone.utc),
        snapshot_id=snap_id,
        universe_version="iso.1",
    )
    assert after == before
    assert "CNStock:999999" not in after
