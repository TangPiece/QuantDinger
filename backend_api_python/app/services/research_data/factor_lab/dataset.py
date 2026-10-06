"""Factor Dataset id 与 Manifest 构建 / 校验。"""

from __future__ import annotations

import hashlib
from typing import Any

from app.services.research_data.contracts import FactorDatasetRecord, FeatureDefinition
from app.services.research_data.hashing import canonical_json

from .models import FactorDatasetManifest


class FactorManifestError(ValueError):
    """Manifest 非法。"""


MANIFEST_REQUIRED = frozenset(
    {
        "factor_code",
        "factor_version",
        "factor_hash",
        "dataset_hash",
        "snapshot_id",
        "schema_version",
        "min_date",
        "max_date",
        "universe",
        "row_count",
        "checksum",
        "layout",
        "engine",
        "engine_version",
    }
)


def compute_factor_dataset_id(
    *,
    factor_hash: str,
    dataset_hash: str,
    snapshot_id: str,
    universe_code: str,
    frequency: str,
    start_date: str,
    end_date: str,
    layout: str,
) -> str:
    """内容寻址 factor_dataset_id。"""
    payload = {
        "factor_hash": factor_hash,
        "dataset_hash": dataset_hash,
        "snapshot_id": snapshot_id,
        "universe": universe_code or "",
        "frequency": frequency,
        "start": start_date,
        "end": end_date,
        "layout": layout,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def build_factor_dataset_record(
    feature: FeatureDefinition,
    *,
    dataset_hash: str,
    snapshot_id: str,
    start_date: str,
    end_date: str,
    universe_code: str = "",
    layout: str = "long",
    storage_uri: str = "",
    checksum: str | None = None,
    row_count: int | None = None,
) -> FactorDatasetRecord:
    """从 Feature + 窗口参数构造 FactorDatasetRecord。"""
    fhash = feature.factor_hash or ""
    if not fhash:
        from .hash import compute_factor_hash

        fhash = compute_factor_hash(feature)
    fid = compute_factor_dataset_id(
        factor_hash=fhash,
        dataset_hash=dataset_hash,
        snapshot_id=snapshot_id,
        universe_code=universe_code or (feature.universe or ""),
        frequency=feature.frequency,
        start_date=start_date,
        end_date=end_date,
        layout=layout,
    )
    return FactorDatasetRecord(
        factor_dataset_id=fid,
        factor_ref=f"{feature.code}@{feature.version}",
        factor_hash=fhash,
        dataset_hash=dataset_hash,
        snapshot_id=snapshot_id,
        universe_code=universe_code or (feature.universe or ""),
        frequency=feature.frequency,
        start_date=start_date,
        end_date=end_date,
        storage_uri=storage_uri,
        checksum=checksum,
        row_count=row_count,
        layout=layout,  # type: ignore[arg-type]
        schema_version=feature.schema_version,
    )


def build_manifest(
    feature: FeatureDefinition,
    record: FactorDatasetRecord,
    *,
    checksum: str,
    row_count: int,
    min_date: str | None = None,
    max_date: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> FactorDatasetManifest:
    """构建完整 Manifest。"""
    return FactorDatasetManifest(
        factor_code=feature.code,
        factor_version=feature.version,
        factor_hash=record.factor_hash,
        dataset_hash=record.dataset_hash,
        snapshot_id=record.snapshot_id,
        schema_version=record.schema_version,
        min_date=min_date or record.start_date,
        max_date=max_date or record.end_date,
        universe=record.universe_code,
        row_count=row_count,
        checksum=checksum,
        layout=record.layout,
        engine=feature.computation_engine,
        engine_version=feature.engine_version or "",
        factor_dataset_id=record.factor_dataset_id,
        frequency=record.frequency,
        storage_uri=record.storage_uri,
        metadata=dict(metadata or {}),
    )


def validate_manifest(manifest: FactorDatasetManifest | dict[str, Any]) -> None:
    """校验 Manifest 必填字段。"""
    if isinstance(manifest, FactorDatasetManifest):
        data = manifest.model_dump(mode="json")
    else:
        data = dict(manifest)
    missing = [k for k in MANIFEST_REQUIRED if k not in data or data[k] in (None, "")]
    # row_count 允许 0
    if "row_count" in missing and data.get("row_count") == 0:
        missing.remove("row_count")
    if "universe" in missing and data.get("universe") == "":
        missing.remove("universe")
    if "engine_version" in missing and data.get("engine_version") == "":
        missing.remove("engine_version")
    if missing:
        raise FactorManifestError(f"manifest missing required fields: {sorted(missing)}")
