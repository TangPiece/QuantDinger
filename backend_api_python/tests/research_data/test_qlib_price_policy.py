"""price_policy 进入 identity；none vs post 缓存分离。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.services.research_data.contracts import DatasetDefinition, PricePolicy
from app.services.research_data.ingest.build_golden import GOLDEN_DATASET_CODE
from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
from app.services.research_data.qlib_materializer.identity import compute_materialization_id


def test_none_and_post_different_materialization(golden_qlib_env):
    query = golden_qlib_env["query"]
    registry = golden_qlib_env["registry"]
    cache_root = golden_qlib_env["cache_root"]
    handle_none = query.dataset(golden_qlib_env["dataset_ref"])

    # 克隆定义但改为 post（新 snapshot 绑定同一事实；hash 因 price_policy 变化）
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
    handle_post = query.dataset(f"{GOLDEN_DATASET_CODE}@v1_post")

    assert handle_none.dataset_hash != handle_post.dataset_hash
    assert compute_materialization_id(handle_none.dataset_hash) != compute_materialization_id(
        handle_post.dataset_hash
    )

    mat = DefaultQlibMaterializer(query, cache_root=cache_root)
    r_none = mat.materialize(golden_qlib_env["dataset_ref"])
    r_post = mat.materialize(f"{GOLDEN_DATASET_CODE}@v1_post")
    assert r_none.materialization_id != r_post.materialization_id

    mani_none = json.loads(Path(r_none.manifest_path).read_text(encoding="utf-8"))
    mani_post = json.loads(Path(r_post.manifest_path).read_text(encoding="utf-8"))
    assert mani_none["price_policy"]["adjustment"] == "none"
    assert mani_post["price_policy"]["adjustment"] == "post"

    # 价格：对 2024-01 样本，post 应因 CA(2024-06-01) 放大
    m_none = query.market(
        ["CNStock:000001"],
        date(2024, 1, 1),
        date(2024, 1, 31),
        price_policy=PricePolicy(adjustment="none"),
    )
    m_post = query.market(
        ["CNStock:000001"],
        date(2024, 1, 1),
        date(2024, 1, 31),
        price_policy=PricePolicy(adjustment="post"),
    )
    assert float(m_post.iloc[0]["close"]) != float(m_none.iloc[0]["close"])
