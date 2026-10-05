"""price_policy：none vs post 结果与 hash 差异。"""

from __future__ import annotations

from datetime import date

import pyarrow as pa
import pytest

from app.services.research_data.contracts import PricePolicy
from app.services.research_data.data_query import DataQuery, DataQueryError
from app.services.research_data.hashing import compute_dataset_hash
from app.services.research_data.writer import write_corporate_action, write_market_daily


def test_none_differs_from_post_and_hashes(research_env):
    store, registry, query = research_env
    market = pa.table(
        {
            "instrument_key": ["CNStock:000001", "CNStock:000001"],
            "trading_date": [date(2024, 5, 1), date(2024, 7, 1)],
            "open": [10.0, 11.0],
            "high": [10.5, 11.5],
            "low": [9.5, 10.5],
            "close": [10.0, 11.0],
            "volume": [1000.0, 1000.0],
            "amount": [10000.0, 11000.0],
            "vwap": [10.0, 11.0],
            "data_version": ["v1", "v1"],
        }
    )
    write_market_daily(
        store, market, exchange="CN", year=2024, month=5, registry=registry, version="v1"
    )
    # 7 月分区也要写（5 月文件只有 5-1 一行时，7-1 需单独分区）
    market_jul = pa.table(
        {
            "instrument_key": ["CNStock:000001"],
            "trading_date": [date(2024, 7, 1)],
            "open": [11.0],
            "high": [11.5],
            "low": [10.5],
            "close": [11.0],
            "volume": [1000.0],
            "amount": [11000.0],
            "vwap": [11.0],
            "data_version": ["v1"],
        }
    )
    write_market_daily(
        store, market_jul, exchange="CN", year=2024, month=7, registry=registry, version="v1"
    )
    # 覆盖：重写 5 月仅含 5-1
    market_may = pa.table(
        {
            "instrument_key": ["CNStock:000001"],
            "trading_date": [date(2024, 5, 1)],
            "open": [10.0],
            "high": [10.5],
            "low": [9.5],
            "close": [10.0],
            "volume": [1000.0],
            "amount": [10000.0],
            "vwap": [10.0],
            "data_version": ["v1"],
        }
    )
    write_market_daily(
        store, market_may, exchange="CN", year=2024, month=5, registry=registry, version="v1"
    )

    ca = pa.table(
        {
            "instrument_key": ["CNStock:000001"],
            "effective_date": [date(2024, 6, 1)],
            "action_type": ["split"],
            "cash_dividend": [0.0],
            "split_ratio": [1.1],
            "rights_ratio": [0.0],
            "rights_price": [0.0],
            "currency": ["CNY"],
            "source": ["test"],
            "source_version": ["v1"],
            "data_version": ["v1"],
        }
    )
    write_corporate_action(
        store, ca, exchange="CN", year=2024, registry=registry, version="v1"
    )

    raw = query.market(
        ["CNStock:000001"],
        date(2024, 5, 1),
        date(2024, 7, 1),
        price_policy=PricePolicy(adjustment="none"),
    )
    post = query.market(
        ["CNStock:000001"],
        date(2024, 5, 1),
        date(2024, 7, 1),
        price_policy=PricePolicy(adjustment="post"),
    )
    assert len(raw) == 2
    assert len(post) == 2
    # 5-1 在 split 之前 → close * 1.1；7-1 在之后 → 不变
    may_raw = float(raw.loc[raw["trading_date"] == date(2024, 5, 1), "close"].iloc[0])
    may_post = float(post.loc[post["trading_date"] == date(2024, 5, 1), "close"].iloc[0])
    jul_raw = float(raw.loc[raw["trading_date"] == date(2024, 7, 1), "close"].iloc[0])
    jul_post = float(post.loc[post["trading_date"] == date(2024, 7, 1), "close"].iloc[0])
    assert may_post == pytest.approx(may_raw * 1.1)
    assert jul_post == pytest.approx(jul_raw)

    h_none = compute_dataset_hash(
        dataset_definition={"code": "x"},
        dataset_version="v1",
        snapshot_id="s",
        schema_version="market_bar_daily@1",
        processor_version="",
        materializer_version="none",
        price_policy={"adjustment": "none", "return_type": "price"},
    )
    h_post = compute_dataset_hash(
        dataset_definition={"code": "x"},
        dataset_version="v1",
        snapshot_id="s",
        schema_version="market_bar_daily@1",
        processor_version="",
        materializer_version="none",
        price_policy={"adjustment": "post", "return_type": "price"},
    )
    assert h_none != h_post


def test_post_without_ca_errors(research_env):
    store, registry, query = research_env
    market = pa.table(
        {
            "instrument_key": ["CNStock:000001"],
            "trading_date": [date(2024, 5, 1)],
            "open": [10.0],
            "high": [10.5],
            "low": [9.5],
            "close": [10.0],
            "volume": [1000.0],
            "amount": [10000.0],
            "vwap": [10.0],
            "data_version": ["v1"],
        }
    )
    write_market_daily(
        store, market, exchange="CN", year=2024, month=5, registry=registry, version="v1"
    )
    with pytest.raises(DataQueryError):
        query.market(
            ["CNStock:000001"],
            date(2024, 5, 1),
            date(2024, 5, 1),
            price_policy=PricePolicy(adjustment="post"),
        )
