"""Universe snapshot：研究读路径不依赖 PG 当前态。"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pyarrow as pa

from app.services.research_data.writer import write_universe_snapshot


def test_universe_asof_from_snapshot_only(seeded_research):
    query = seeded_research["query"]
    # 2024：999999 已退出
    members = query.universe(
        "CSI300",
        datetime(2024, 6, 1, tzinfo=timezone.utc),
        universe_version="2024.05",
        snapshot_id=seeded_research["snapshot_id"],
    )
    assert members == ["CNStock:000001"]

    # 2022：两只都在
    members_old = query.universe(
        "CSI300",
        datetime(2022, 6, 1, tzinfo=timezone.utc),
        universe_version="2024.05",
        snapshot_id=seeded_research["snapshot_id"],
    )
    assert set(members_old) == {"CNStock:000001", "CNStock:999999"}


def test_rewriting_snapshot_version_does_not_affect_old_version(research_env):
    store, registry, query = research_env
    snap_a = "snap_a"
    table_a = pa.table(
        {
            "universe_code": pa.array(["DEMO"]),
            "universe_version": pa.array(["v1"]),
            "instrument_key": pa.array(["CNStock:A"]),
            "valid_from": pa.array([date(2020, 1, 1)], type=pa.date32()),
            "valid_to": pa.array([None], type=pa.date32()),
            "weight": pa.array([1.0], type=pa.float64()),
            "member_rank": pa.array([1], type=pa.int32()),
            "source_version": pa.array(["x"]),
            "snapshot_id": pa.array([snap_a]),
        }
    )
    write_universe_snapshot(
        store, table_a, universe_code="DEMO", universe_version="v1", registry=registry
    )
    # 新版本只含 B
    table_b = pa.table(
        {
            "universe_code": pa.array(["DEMO"]),
            "universe_version": pa.array(["v2"]),
            "instrument_key": pa.array(["CNStock:B"]),
            "valid_from": pa.array([date(2020, 1, 1)], type=pa.date32()),
            "valid_to": pa.array([None], type=pa.date32()),
            "weight": pa.array([1.0], type=pa.float64()),
            "member_rank": pa.array([1], type=pa.int32()),
            "source_version": pa.array(["x"]),
            "snapshot_id": pa.array(["snap_b"]),
        }
    )
    write_universe_snapshot(
        store, table_b, universe_code="DEMO", universe_version="v2", registry=registry
    )
    assert query.universe(
        "DEMO", datetime(2024, 1, 1, tzinfo=timezone.utc), universe_version="v1"
    ) == ["CNStock:A"]
    assert query.universe(
        "DEMO", datetime(2024, 1, 1, tzinfo=timezone.utc), universe_version="v2"
    ) == ["CNStock:B"]
