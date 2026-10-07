"""写入 def.json 与 manifest.json。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.services.research_data.contracts import ArtifactRecord, DatasetDefinition

from .artifact_store import DatasetArtifactStore
from .protocol import DatasetManifest, definition_summary


@dataclass
class DatasetWriteResult:
    def_path: str
    manifest_path: str
    manifest_uri: str
    def_checksum: str
    manifest_checksum: str


def write_dataset_artifacts(
    store: DatasetArtifactStore,
    *,
    definition: DatasetDefinition,
    manifest: DatasetManifest,
    manifest_uri: str,
) -> DatasetWriteResult:
    """落盘 def.json + manifest.json；manifest_uri 由调用方解析（本地 path 或 r2）。"""
    def_payload: dict[str, Any] = {
        "schema_version": "dataset_def@1",
        "definition": definition_summary(definition),
        "dataset_hash": manifest.dataset_hash,
        "published_at": _iso(manifest.published_at),
    }
    def_text = json.dumps(def_payload, ensure_ascii=False, indent=2, default=str)
    def_file = store.def_path(definition)
    def_file.parent.mkdir(parents=True, exist_ok=True)
    def_file.write_text(def_text, encoding="utf-8")
    def_cs = hashlib.sha256(def_text.encode("utf-8")).hexdigest()

    man_payload = manifest.model_dump(mode="json")
    man_text = json.dumps(man_payload, ensure_ascii=False, indent=2, default=str)
    man_file = store.manifest_path(definition)
    man_file.parent.mkdir(parents=True, exist_ok=True)
    man_file.write_text(man_text, encoding="utf-8")
    man_cs = hashlib.sha256(man_text.encode("utf-8")).hexdigest()

    return DatasetWriteResult(
        def_path=str(def_file.resolve()),
        manifest_path=str(man_file.resolve()),
        manifest_uri=manifest_uri,
        def_checksum=def_cs,
        manifest_checksum=man_cs,
    )


def artifact_record_from_write(result: DatasetWriteResult) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=result.manifest_checksum[:32],
        artifact_type="research_dataset_manifest",
        storage_uri=result.manifest_uri,
        checksum=result.manifest_checksum,
        size_bytes=0,
        metadata={
            "def_path": result.def_path,
            "manifest_path": result.manifest_path,
            "def_checksum": result.def_checksum,
        },
    )


def _iso(ts: datetime) -> str:
    from datetime import timezone

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "DatasetWriteResult",
    "artifact_record_from_write",
    "write_dataset_artifacts",
]
