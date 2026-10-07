"""薄封装：domain dataset_hash 仍走 research_data.hashing（算法锁死）。"""

from __future__ import annotations

from app.services.research_data.contracts import DatasetDefinition
from app.services.research_data.hashing import canonical_json, compute_dataset_hash

DOMAIN_MATERIALIZER_VERSION = "none"


def compute_domain_dataset_hash(definition: DatasetDefinition) -> str:
    """与 Registry.get_dataset 一致的 domain hash。"""
    return compute_dataset_hash(
        dataset_definition=definition.model_dump(mode="json"),
        dataset_version=definition.version,
        snapshot_id=definition.snapshot_id,
        schema_version=definition.schema_version,
        processor_version=definition.processor or "",
        materializer_version=DOMAIN_MATERIALIZER_VERSION,
        price_policy=definition.price_policy.model_dump(mode="json"),
    )


__all__ = [
    "DOMAIN_MATERIALIZER_VERSION",
    "canonical_json",
    "compute_dataset_hash",
    "compute_domain_dataset_hash",
]
