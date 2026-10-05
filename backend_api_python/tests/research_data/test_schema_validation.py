"""Parquet schema 校验。"""

from __future__ import annotations

from datetime import date

import pyarrow as pa
import pytest

from app.services.research_data.canonical_store import LocalCanonicalStore
from app.services.research_data.schemas import SchemaValidationError, market_bar_daily_schema
from app.services.research_data.writer import put_parquet


def test_put_parquet_rejects_missing_columns(tmp_path):
    store = LocalCanonicalStore(root=tmp_path)
    bad = pa.table({"instrument_key": ["CNStock:1"], "close": [1.0]})
    with pytest.raises(SchemaValidationError):
        put_parquet(
            store,
            "qd/canonical/market/daily/bad.parquet",
            bad,
            expected_schema=market_bar_daily_schema(),
            required_columns=["instrument_key", "trading_date", "open", "high", "low", "close"],
        )


def test_put_parquet_accepts_valid_market(tmp_path):
    store = LocalCanonicalStore(root=tmp_path)
    good = pa.table(
        {
            "instrument_key": ["CNStock:1"],
            "trading_date": [date(2024, 1, 2)],
            "open": [1.0],
            "high": [1.1],
            "low": [0.9],
            "close": [1.05],
            "volume": [1.0],
            "amount": [1.0],
            "vwap": [1.0],
            "data_version": ["v"],
        }
    )
    checksum = put_parquet(
        store,
        "qd/canonical/market/daily/ok.parquet",
        good,
        expected_schema=market_bar_daily_schema(),
    )
    assert len(checksum) == 64
    assert store.exists("qd/canonical/market/daily/ok.parquet")
