"""从 Definition + Snapshot 组装 pinned manifest。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.research_data.contracts import DatasetDefinition

from .hashing import compute_domain_dataset_hash
from .identity import dataset_definition_key, manifest_r2_key
from .protocol import DatasetLineageItem, DatasetManifest, ENGINE_VERSION, MANIFEST_SCHEMA_VERSION


def _lineage_from_items(items: list[dict[str, Any]]) -> list[DatasetLineageItem]:
    out: list[DatasetLineageItem] = []
    for raw in items:
        out.append(
            DatasetLineageItem(
                dataset_code=str(raw.get("dataset_code") or ""),
                version=str(raw.get("version") or ""),
                path=str(raw.get("path") or ""),
                checksum=str(raw.get("checksum") or ""),
                r2_uri=str(raw.get("r2_uri") or raw.get("path") or ""),
            )
        )
    return out


def pin_manifest(
    definition: DatasetDefinition,
    *,
    snapshot_items: list[dict[str, Any]],
    dataset_hash: str,
    published_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> DatasetManifest:
    """构建待写入的 DatasetManifest（immutable=True）。"""
    ts = published_at or datetime.now(timezone.utc)
    return DatasetManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        engine_version=ENGINE_VERSION,
        dataset_code=definition.code,
        dataset_version=definition.version,
        snapshot_id=definition.snapshot_id,
        dataset_hash=dataset_hash,
        name=definition.name,
        frequency=definition.frequency,
        universe_code=definition.universe_code,
        universe_version=definition.universe_version,
        schema_version_ref=definition.schema_version,
        features=list(definition.features or []),
        label=definition.label,
        processor=definition.processor or "",
        price_policy=definition.price_policy,
        pit=definition.pit,
        lineage=_lineage_from_items(snapshot_items),
        immutable=True,
        published_at=ts,
        r2_key=manifest_r2_key(definition),
        def_r2_key=dataset_definition_key(
            dataset_code=definition.code, dataset_version=definition.version
        ),
        metadata=metadata or {},
    )


def pin_definition_hash(definition: DatasetDefinition) -> str:
    return compute_domain_dataset_hash(definition)


__all__ = ["pin_definition_hash", "pin_manifest"]
