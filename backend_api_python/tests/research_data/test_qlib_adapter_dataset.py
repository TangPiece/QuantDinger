"""Phase 2A：QlibAdapter build_handler / 与 DataQuery 一致性。"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("qlib")
from qlib.data import D

from app.services.research_data.qlib_adapter import QlibAdapter
from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
from app.services.research_data.qlib_materializer.validation import compare_feature_values


def test_build_handler_fetch_and_consistency(golden_qlib_env):
    """Handler 非空；Adapter 激活后 D.features($close) 与 DataQuery 一致。"""
    query = golden_qlib_env["query"]
    adapter = QlibAdapter(
        query,
        materializer=golden_qlib_env["materializer"],
        registry=golden_qlib_env["registry"],
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    bundle = adapter.resolve(golden_qlib_env["dataset_ref"])
    assert bundle.dataset_hash
    assert bundle.bundle_hash

    handler = adapter.build_handler(
        golden_qlib_env["dataset_ref"],
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
        force_materialize=True,
    )
    df = handler.fetch(col_set="feature")
    if df is None or len(df) == 0:
        df = handler.fetch()
    assert df is not None and len(df) > 0

    # 一致性：经 Adapter Runtime 激活的 provider，用 D.features 读 $close
    ik = "CNStock:000001"
    qlib_id = to_qlib_instrument(ik).lower()
    market = query.market(
        [ik],
        date(2024, 1, 1),
        date(2024, 6, 30),
        price_policy=bundle.handle.definition.price_policy,
    )
    assert not market.empty
    start = str(market["trading_date"].min())
    end = str(market["trading_date"].max())
    feat = D.features([qlib_id], ["$close"], start_time=start, end_time=end)
    assert len(feat) > 0
    dq_vals = [float(x) for x in market.sort_values("trading_date")["close"].tolist()]
    q_vals = [float(x) for x in feat.iloc[:, 0].tolist()]
    n = min(len(dq_vals), len(q_vals))
    assert n > 0
    compare_feature_values(dq_vals[:n], q_vals[:n], atol=1e-8, rtol=1e-6)


def test_build_dataset_placeholder(golden_qlib_env):
    adapter = QlibAdapter(
        golden_qlib_env["query"],
        materializer=golden_qlib_env["materializer"],
        registry=golden_qlib_env["registry"],
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    ds = adapter.build_dataset(
        golden_qlib_env["dataset_ref"],
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
        force_materialize=True,
    )
    assert ds is not None
