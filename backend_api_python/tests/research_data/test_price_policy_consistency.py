"""price_policy 一致性：raw Canonical + none 政策与 dataset_hash 绑定。"""

from __future__ import annotations

from datetime import date

from app.services.research_data.contracts import PricePolicy
from app.services.research_data.hashing import compute_dataset_hash


def test_market_returns_raw_prices_under_none_policy(seeded_research):
    query = seeded_research["query"]
    df = query.market(
        ["CNStock:000001"],
        date(2024, 5, 1),
        date(2024, 5, 1),
        price_policy=PricePolicy(adjustment="none"),
    )
    assert float(df.iloc[0]["close"]) == 10.5


def test_dataset_handle_embeds_price_policy_in_hash(seeded_research):
    handle = seeded_research["query"].dataset(seeded_research["dataset_ref"])
    expected = compute_dataset_hash(
        dataset_definition=handle.definition.model_dump(mode="json"),
        dataset_version=handle.definition.version,
        snapshot_id=handle.definition.snapshot_id,
        schema_version=handle.definition.schema_version,
        processor_version=handle.definition.processor or "",
        materializer_version="none",
        price_policy=handle.definition.price_policy.model_dump(mode="json"),
    )
    assert handle.dataset_hash == expected
    other = compute_dataset_hash(
        dataset_definition=handle.definition.model_dump(mode="json"),
        dataset_version=handle.definition.version,
        snapshot_id=handle.definition.snapshot_id,
        schema_version=handle.definition.schema_version,
        processor_version=handle.definition.processor or "",
        materializer_version="none",
        price_policy={"adjustment": "post", "return_type": "price"},
    )
    assert handle.dataset_hash != other
