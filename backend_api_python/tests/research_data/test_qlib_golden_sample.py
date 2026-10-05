"""Golden Sample：DataQuery vs Qlib D.features 数值一致（tolerance）。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("qlib")
import qlib
from qlib.data import D

from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
from app.services.research_data.qlib_materializer.validation import compare_feature_values


def test_golden_sample_via_d_features(golden_qlib_env):
    """主验收：经 Qlib API 读回，与 DataQuery 一致。"""
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

    instruments = query.universe(
        handle.definition.universe_code,
        date(2024, 3, 1),
        snapshot_id=handle.definition.snapshot_id,
        universe_version=handle.definition.universe_version,
    )[:10]
    market = query.market(
        instruments,
        date(1970, 1, 1),
        date(2100, 1, 1),
        price_policy=handle.definition.price_policy,
    )
    dates = sorted(set(market["trading_date"].tolist()))[:20]
    market = market[market["trading_date"].isin(dates)]

    for ik in instruments:
        qlib_id = to_qlib_instrument(ik).lower()
        part = market[market["instrument_key"] == ik].sort_values("trading_date")
        if part.empty:
            continue
        start = str(part.iloc[0]["trading_date"])
        end = str(part.iloc[-1]["trading_date"])
        feat = D.features([qlib_id], ["$close"], start_time=start, end_time=end)
        assert len(feat) > 0
        dq_vals = [float(x) for x in part["close"].tolist()]
        q_vals = [float(x) for x in feat.iloc[:, 0].tolist()]
        n = min(len(dq_vals), len(q_vals))
        compare_feature_values(dq_vals[:n], q_vals[:n], atol=1e-8, rtol=1e-6)


def test_bin_has_start_index_header(golden_qlib_env):
    """辅助：裸 bin 首元素为 start_index=0，数值从下标 1 开始。"""
    mat = golden_qlib_env["materializer"]
    result = mat.materialize(golden_qlib_env["dataset_ref"], force=True)
    bin_path = Path(result.cache_path) / "features" / "sz000001" / "close.day.bin"
    arr = np.fromfile(bin_path, dtype="<f4")
    assert len(arr) >= 2
    assert float(arr[0]) == 0.0  # start_index
    # 缺失语义：NaN 不应被写成 0 填充整段
    assert not np.all(arr[1:] == 0)
