"""Phase 1D：dataset_hash / materialization 可复现与 price_policy 分叉。"""

from __future__ import annotations

from app.services.research_data.contracts import DatasetDefinition, PricePolicy
from app.services.research_data.ingest.build_golden import GOLDEN_DATASET_CODE
from app.services.research_data.qlib_materializer import DefaultQlibMaterializer
from app.services.research_data.qlib_materializer.identity import compute_materialization_id


def test_rematerialize_stable_hash_and_checksum(golden_qlib_env):
    """同定义 force 两次 → 同 dataset_hash / materialization_id / checksum。"""
    mat = golden_qlib_env["materializer"]
    ref = golden_qlib_env["dataset_ref"]
    a = mat.materialize(ref, force=True)
    b = mat.materialize(ref, force=True)
    assert a.dataset_hash == b.dataset_hash
    assert a.materialization_id == b.materialization_id
    assert a.checksum == b.checksum
    assert a.materialization_id == compute_materialization_id(a.dataset_hash)


def test_price_policy_change_forks_hash(golden_qlib_env):
    """改 price_policy → dataset_hash / materialization_id 变化。"""
    query = golden_qlib_env["query"]
    registry = golden_qlib_env["registry"]
    handle = query.dataset(golden_qlib_env["dataset_ref"])
    post_def = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version="v1_hash_fork",
        name="hash fork",
        frequency="1d",
        universe_code=handle.definition.universe_code,
        universe_version=handle.definition.universe_version,
        snapshot_id=handle.definition.snapshot_id,
        schema_version=handle.definition.schema_version,
        features=handle.definition.features,
        price_policy=PricePolicy(adjustment="post", return_type="price"),
        pit=True,
    )
    registry.upsert_dataset(post_def, status="validated")
    h_post = query.dataset(f"{GOLDEN_DATASET_CODE}@v1_hash_fork")
    assert handle.dataset_hash != h_post.dataset_hash
    assert compute_materialization_id(handle.dataset_hash) != compute_materialization_id(
        h_post.dataset_hash
    )

    mat = DefaultQlibMaterializer(
        query,
        cache_root=golden_qlib_env["cache_root"],
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    r0 = mat.materialize(golden_qlib_env["dataset_ref"], force=True)
    r1 = mat.materialize(f"{GOLDEN_DATASET_CODE}@v1_hash_fork", force=True)
    assert r0.dataset_hash != r1.dataset_hash
    assert r0.materialization_id != r1.materialization_id
