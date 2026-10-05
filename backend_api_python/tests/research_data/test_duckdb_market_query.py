"""DuckDB 路径查询 OHLCV 列齐全、dtype/排序稳定。"""

from __future__ import annotations

from datetime import date

import pyarrow as pa

from app.services.research_data.canonical_repository import CanonicalRepository
from app.services.research_data.contracts import PricePolicy
from app.services.research_data.writer import write_market_daily


REQUIRED_COLS = [
    "instrument_key",
    "trading_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "vwap",
]


def test_duckdb_market_columns_and_order(research_env):
    store, registry, query = research_env
    market = pa.table(
        {
            "instrument_key": ["CNStock:000002", "CNStock:000001"],
            "trading_date": [date(2024, 3, 2), date(2024, 3, 1)],
            "open": [20.0, 10.0],
            "high": [21.0, 11.0],
            "low": [19.0, 9.0],
            "close": [20.5, 10.5],
            "volume": [2000.0, 1000.0],
            "amount": [41000.0, 10500.0],
            "vwap": [20.5, 10.5],
            "data_version": ["v1", "v1"],
        }
    )
    write_market_daily(
        store, market, exchange="CN", year=2024, month=3, registry=registry, version="v1"
    )

    repo = CanonicalRepository(store)
    df = repo.read_parquet_df(
        prefix="qd/canonical/market/daily/exchange=CN/year=2024/month=03",
        order_by=("instrument_key", "trading_date"),
    )
    for col in REQUIRED_COLS:
        assert col in df.columns

    # 排序稳定：instrument_key 升序
    keys = df["instrument_key"].astype(str).tolist()
    assert keys == sorted(keys)

    # DataQuery 走同一 Repository
    out = query.market(
        ["CNStock:000001", "CNStock:000002"],
        date(2024, 3, 1),
        date(2024, 3, 31),
        price_policy=PricePolicy(adjustment="none"),
    )
    for col in REQUIRED_COLS:
        assert col in out.columns
    assert len(out) == 2
