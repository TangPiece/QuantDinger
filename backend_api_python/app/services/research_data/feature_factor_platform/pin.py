"""钉住 9A DatasetHandle 与 Build 索引。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.research_data.contracts import DatasetHandle, FactorDatasetRecord

from .identity import factor_build_index_key, feature_set_build_index_key
from .protocol import (
    ENGINE_VERSION,
    FACTOR_BUILD_INDEX_SCHEMA,
    FactorBuildIndex,
    FeatureSetBuildIndex,
)


def pin_factor_build_index(
    *,
    factor_ref: str,
    factor_hash: str,
    dataset_ref: str,
    handle: DatasetHandle,
    layout: str,
    start_date: str,
    end_date: str,
    record: FactorDatasetRecord,
    parquet_index: list[dict[str, Any]] | None = None,
    published_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> FactorBuildIndex:
    ts = published_at or datetime.now(timezone.utc)
    return FactorBuildIndex(
        schema_version=FACTOR_BUILD_INDEX_SCHEMA,
        engine_version=ENGINE_VERSION,
        factor_ref=factor_ref,
        factor_hash=factor_hash,
        dataset_ref=dataset_ref,
        dataset_hash=handle.dataset_hash,
        snapshot_id=handle.definition.snapshot_id,
        layout=layout,  # type: ignore[arg-type]
        start_date=start_date,
        end_date=end_date,
        factor_dataset_id=record.factor_dataset_id,
        manifest_uri=record.storage_uri or "",
        parquet_index=list(parquet_index or []),
        immutable=True,
        published_at=ts,
        metadata={
            "r2_key": factor_build_index_key(
                factor_ref=factor_ref,
                dataset_hash=handle.dataset_hash,
                layout=layout,
                start_date=start_date,
                end_date=end_date,
            ),
            **(metadata or {}),
        },
    )


def pin_feature_set_build_index(
    *,
    feature_set_ref: str,
    feature_set_hash: str,
    dataset_ref: str,
    handle: DatasetHandle,
    layout: str,
    start_date: str,
    end_date: str,
    member_builds: list[dict[str, Any]],
    published_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> FeatureSetBuildIndex:
    ts = published_at or datetime.now(timezone.utc)
    return FeatureSetBuildIndex(
        engine_version=ENGINE_VERSION,
        feature_set_ref=feature_set_ref,
        feature_set_hash=feature_set_hash,
        dataset_ref=dataset_ref,
        dataset_hash=handle.dataset_hash,
        snapshot_id=handle.definition.snapshot_id,
        layout=layout,  # type: ignore[arg-type]
        start_date=start_date,
        end_date=end_date,
        member_builds=list(member_builds),
        immutable=True,
        published_at=ts,
        metadata={
            "r2_key": feature_set_build_index_key(
                feature_set_ref=feature_set_ref,
                dataset_hash=handle.dataset_hash,
                layout=layout,
                start_date=start_date,
                end_date=end_date,
            ),
            **(metadata or {}),
        },
    )


__all__ = ["pin_factor_build_index", "pin_feature_set_build_index"]
