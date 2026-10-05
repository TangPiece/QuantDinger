"""Phase 1D：DataQuery vs Qlib D.features 全字段 OHLCV 面板一致性。"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("qlib")
import qlib
from qlib.data import D

from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
from app.services.research_data.qlib_materializer.validation import (
    OHLCV_FIELDS,
    compare_ohlcv_panels,
    qlib_features_to_frame,
)


def test_phase1d_ohlcv_panel_consistency(golden_qlib_env):
    """行数 / 股票集 / 交易日集 / open..amount 与 DataQuery 一致。"""
    query = golden_qlib_env["query"]
    mat = golden_qlib_env["materializer"]
    ref = golden_qlib_env["dataset_ref"]
    handle = query.dataset(ref)
    result = mat.materialize(ref, force=True)

    qlib.init(
        provider_uri=result.cache_path,
        region="cn",
        expression_cache=None,
        dataset_cache=None,
        kernels=1,
    )

    as_of = golden_qlib_env["end"]
    members = query.universe(
        handle.definition.universe_code,
        as_of,
        snapshot_id=handle.definition.snapshot_id,
        universe_version=handle.definition.universe_version,
    )
    assert members, "universe at dataset end must be non-empty"

    market = query.market(
        members,
        golden_qlib_env["start"],
        as_of,
        price_policy=handle.definition.price_policy,
    )
    assert not market.empty

    qlib_ids = [to_qlib_instrument(ik).lower() for ik in members]
    fields = [f"${f}" for f in OHLCV_FIELDS]
    start = str(min(market["trading_date"].tolist()))
    end = str(max(market["trading_date"].tolist()))
    feat = D.features(qlib_ids, fields, start_time=start, end_time=end)
    assert len(feat) > 0

    qlib_df = qlib_features_to_frame(feat, fields=OHLCV_FIELDS)
    # 只比对双方都有行情的 (instrument, date)——D.features 会对缺行情票吐出日历 NaN 行
    market_keys = set(
        zip(
            market["instrument_key"].map(lambda x: to_qlib_instrument(str(x)).lower()),
            market["trading_date"].map(lambda d: d.date() if hasattr(d, "date") else d),
        )
    )
    qlib_df = qlib_df[
        qlib_df.apply(
            lambda r: (r["qlib_instrument"], r["trading_date"]) in market_keys,
            axis=1,
        )
    ].reset_index(drop=True)

    summary = compare_ohlcv_panels(market, qlib_df, fields=OHLCV_FIELDS)
    assert summary["rows"] == len(market)
    assert summary["dates"] == market["trading_date"].nunique()
