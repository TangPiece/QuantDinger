"""Phase 1D：price_policy 经 Qlib D.features 与 DataQuery 一致；Canonical 不被改写。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("qlib")
import qlib
from qlib.data import D

from app.services.research_data.contracts import DatasetDefinition, PricePolicy
from app.services.research_data.ingest.build_golden import GOLDEN_DATASET_CODE
from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
from app.services.research_data.qlib_materializer.instrument_mapper import to_qlib_instrument
from app.services.research_data.qlib_materializer.validation import (
    assert_canonical_raw_unchanged,
    compare_feature_values,
    directory_sha256,
)


def test_none_and_post_via_d_features(golden_qlib_env):
    """none/post 物化后 D.features($close) 与对应 DataQuery.market 一致，且 post≠none。"""
    query = golden_qlib_env["query"]
    registry = golden_qlib_env["registry"]
    cache_root = golden_qlib_env["cache_root"]
    store = golden_qlib_env["store"]
    handle_none = query.dataset(golden_qlib_env["dataset_ref"])

    before = directory_sha256(Path(store.root))

    post_def = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version="v1_post",
        name="post variant",
        frequency="1d",
        universe_code=handle_none.definition.universe_code,
        universe_version=handle_none.definition.universe_version,
        snapshot_id=handle_none.definition.snapshot_id,
        schema_version=handle_none.definition.schema_version,
        features=handle_none.definition.features,
        price_policy=PricePolicy(adjustment="post", return_type="price"),
        pit=True,
    )
    registry.upsert_dataset(post_def, status="validated")

    mat = DefaultQlibMaterializer(
        query,
        cache_root=cache_root,
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    r_none = mat.materialize(golden_qlib_env["dataset_ref"], force=True)
    r_post = mat.materialize(f"{GOLDEN_DATASET_CODE}@v1_post", force=True)
    assert r_none.dataset_hash != r_post.dataset_hash

    after = directory_sha256(Path(store.root))
    assert_canonical_raw_unchanged(before, after)

    ik = "CNStock:000001"
    qlib_id = to_qlib_instrument(ik).lower()
    # CA @ 2024-06-01：取 1 月窗口，post 应放大
    start, end = date(2024, 1, 1), date(2024, 1, 31)
    m_none = query.market([ik], start, end, price_policy=PricePolicy(adjustment="none"))
    m_post = query.market([ik], start, end, price_policy=PricePolicy(adjustment="post"))
    assert float(m_post.iloc[0]["close"]) != float(m_none.iloc[0]["close"])

    for result, market in ((r_none, m_none), (r_post, m_post)):
        qlib.init(
            provider_uri=result.cache_path,
            region="cn",
            expression_cache=None,
            dataset_cache=None,
            kernels=1,
        )
        feat = D.features(
            [qlib_id],
            ["$close"],
            start_time=start.isoformat(),
            end_time=end.isoformat(),
        )
        assert len(feat) > 0
        dq_vals = [float(x) for x in market.sort_values("trading_date")["close"].tolist()]
        q_vals = [float(x) for x in feat.iloc[:, 0].tolist()]
        n = min(len(dq_vals), len(q_vals))
        compare_feature_values(dq_vals[:n], q_vals[:n], atol=1e-8, rtol=1e-6)


def test_pre_adjustment_still_not_implemented(golden_qlib_env):
    """pre / hfq 仍未实现。"""
    query = golden_qlib_env["query"]
    with pytest.raises(NotImplementedError):
        query.market(
            ["CNStock:000001"],
            date(2024, 1, 1),
            date(2024, 1, 31),
            price_policy=PricePolicy(adjustment="pre"),
        )
