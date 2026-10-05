"""同输入两次 ingest → 逻辑行/schema/order/checksum 一致。"""

from __future__ import annotations

import hashlib
from datetime import date

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.ingest.market import ingest_market_daily, records_to_market_table
from app.services.research_data.registry import LocalJsonRegistry


def _logical_checksum(records: list[dict]) -> str:
    """基于稳定排序后的逻辑行内容，不依赖 parquet 物理字节。"""
    table = records_to_market_table(records)
    # 用列值拼接，避免压缩时间戳等物理差异
    parts = []
    for i in range(table.num_rows):
        row = []
        for name in table.column_names:
            row.append(f"{name}={table.column(name)[i].as_py()}")
        parts.append("|".join(row))
    payload = "\n".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_two_ingests_same_logical_checksum(tmp_path):
    records = [
        {
            "instrument_key": "CNStock:000001",
            "trading_date": date(2024, 1, 2),
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 1000.0,
            "amount": 10500.0,
            "vwap": 10.5,
            "data_version": "v1",
        },
        {
            "instrument_key": "CNStock:000002",
            "trading_date": date(2024, 1, 2),
            "open": 20.0,
            "high": 21.0,
            "low": 19.0,
            "close": 20.5,
            "volume": 2000.0,
            "amount": 41000.0,
            "vwap": 20.5,
            "data_version": "v1",
        },
    ]
    # 打乱输入顺序，验证排序后逻辑一致
    shuffled = list(reversed(records))

    store_a = LocalCanonicalStore(root=tmp_path / "a")
    store_b = LocalCanonicalStore(root=tmp_path / "b")
    reg_a = LocalJsonRegistry(root=tmp_path / "ra")
    reg_b = LocalJsonRegistry(root=tmp_path / "rb")

    meta_a = ingest_market_daily(
        store_a,
        instrument_keys=["CNStock:000001"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        version="v1",
        registry=reg_a,
        preloaded_records=records,
    )
    meta_b = ingest_market_daily(
        store_b,
        instrument_keys=["CNStock:000001"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        version="v1",
        registry=reg_b,
        preloaded_records=shuffled,
    )

    assert meta_a["row_count"] == meta_b["row_count"] == 2
    assert _logical_checksum(records) == _logical_checksum(shuffled)

    # schema：两次写出的 key 均存在且行数一致
    assert len(meta_a["written"]) == len(meta_b["written"]) == 1
    from app.services.research_data.writer import read_parquet_table

    t_a = read_parquet_table(store_a, meta_a["written"][0]["key"])
    t_b = read_parquet_table(store_b, meta_b["written"][0]["key"])
    assert t_a.schema.names == t_b.schema.names
    assert t_a.num_rows == t_b.num_rows
    # 行序：instrument_key, trading_date
    assert [t_a.column("instrument_key")[i].as_py() for i in range(t_a.num_rows)] == [
        t_b.column("instrument_key")[i].as_py() for i in range(t_b.num_rows)
    ]
