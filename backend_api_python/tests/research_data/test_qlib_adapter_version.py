"""Phase 2A：VersionResolver + bundle_hash。"""

from __future__ import annotations

from app.services.research_data.contracts import DatasetDefinition, PricePolicy
from app.services.research_data.ingest.build_golden import GOLDEN_DATASET_CODE
from app.services.research_data.qlib_adapter import (
    ADAPTER_VERSION,
    VersionResolver,
    builtin_cs_zscore_processor,
    builtin_identity_processor,
    compute_bundle_hash,
)


def test_bundle_hash_stable_and_processor_sensitive(golden_qlib_env):
    query = golden_qlib_env["query"]
    registry = golden_qlib_env["registry"]
    registry.upsert_processor(builtin_identity_processor())
    registry.upsert_processor(builtin_cs_zscore_processor())

    resolver = VersionResolver(query, registry)
    a = resolver.resolve(golden_qlib_env["dataset_ref"])
    b = resolver.resolve(golden_qlib_env["dataset_ref"])
    assert a.dataset_hash == b.dataset_hash
    assert a.bundle_hash == b.bundle_hash
    assert a.adapter_version == ADAPTER_VERSION
    assert a.processor_version == "none"
    assert a.bundle_hash == compute_bundle_hash(
        dataset_hash=a.dataset_hash,
        adapter_version=ADAPTER_VERSION,
        processor_version="none",
        pipeline_digest="none",
    )
    assert a.pipeline_digest == "none"

    handle = query.dataset(golden_qlib_env["dataset_ref"])
    post_def = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version="v1_proc",
        name="with processor",
        frequency="1d",
        universe_code=handle.definition.universe_code,
        universe_version=handle.definition.universe_version,
        snapshot_id=handle.definition.snapshot_id,
        schema_version=handle.definition.schema_version,
        features=handle.definition.features,
        price_policy=handle.definition.price_policy,
        processor="cs_zscore@1",
        pit=True,
    )
    registry.upsert_dataset(post_def, status="validated")
    c = resolver.resolve(f"{GOLDEN_DATASET_CODE}@v1_proc")
    assert c.processor_version == "cs_zscore@1"
    assert c.bundle_hash != a.bundle_hash
    # Domain dataset_hash 也因 processor 字段变化而变
    assert c.dataset_hash != a.dataset_hash
