"""写入 FeatureSet manifest 与 Build 索引。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from .artifact_store import FeatureFactorArtifactStore
from .feature_set import FeatureSetDefinition
from .protocol import FactorBuildIndex, FeatureSetBuildIndex, FeatureSetManifest


@dataclass
class WriteResult:
    path: str
    checksum: str


def write_feature_set_manifest(
    store: FeatureFactorArtifactStore,
    definition: FeatureSetDefinition,
    manifest: FeatureSetManifest,
) -> WriteResult:
    path = store.feature_set_manifest_path(code=definition.code, version=definition.version)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    cs = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return WriteResult(path=str(path.resolve()), checksum=cs)


def write_factor_build_index(
    store: FeatureFactorArtifactStore,
    index: FactorBuildIndex,
) -> WriteResult:
    path = store.factor_build_index_path(
        factor_ref=index.factor_ref,
        dataset_hash=index.dataset_hash,
        layout=index.layout,
        start_date=index.start_date,
        end_date=index.end_date,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(index.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    cs = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return WriteResult(path=str(path.resolve()), checksum=cs)


def write_feature_set_build_index(
    store: FeatureFactorArtifactStore,
    index: FeatureSetBuildIndex,
) -> WriteResult:
    path = store.feature_set_build_index_path(
        feature_set_ref=index.feature_set_ref,
        dataset_hash=index.dataset_hash,
        layout=index.layout,
        start_date=index.start_date,
        end_date=index.end_date,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(index.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    cs = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return WriteResult(path=str(path.resolve()), checksum=cs)


def iso_ts(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "WriteResult",
    "write_factor_build_index",
    "write_feature_set_build_index",
    "write_feature_set_manifest",
]
