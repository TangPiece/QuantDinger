"""Artifact Bundle Manifest（挂 Bundle，非 Version repro）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

MANIFEST_SCHEMA = "model_artifact_manifest@1"


class _ManModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactContentInfo(_ManModel):
    path: str = "model.bin"
    size: int = 0
    checksum: str = ""
    checksum_algorithm: str = "SHA256"


class ArtifactLineageInfo(_ManModel):
    dataset_hash: str = ""
    feature_set_hash: str = ""
    label_hash: str = ""
    processor_version: str = ""
    training_config_hash: str = ""
    snapshot_id: str = ""


class ArtifactManifest(_ManModel):
    schema_version: str = MANIFEST_SCHEMA
    artifact_id: str
    artifact_type: str = "MODEL"
    model_id: str = ""
    model_version_id: str = ""
    training_run_id: str = ""
    framework: str = ""
    framework_version: str = ""
    content: ArtifactContentInfo = Field(default_factory=ArtifactContentInfo)
    lineage: ArtifactLineageInfo = Field(default_factory=ArtifactLineageInfo)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_artifact_manifest(
    *,
    artifact_id: str,
    training_run_id: str = "",
    model_id: str = "",
    model_version_id: str = "",
    framework: str = "",
    framework_version: str = "",
    checksum: str = "",
    file_size: int = 0,
    lineage: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ArtifactManifest:
    lin = dict(lineage or {})
    return ArtifactManifest(
        artifact_id=artifact_id,
        training_run_id=training_run_id,
        model_id=model_id,
        model_version_id=model_version_id,
        framework=framework,
        framework_version=framework_version,
        content=ArtifactContentInfo(
            path="model.bin",
            size=int(file_size or 0),
            checksum=checksum,
            checksum_algorithm="SHA256",
        ),
        lineage=ArtifactLineageInfo(
            dataset_hash=str(lin.get("dataset_hash") or ""),
            feature_set_hash=str(lin.get("feature_set_hash") or ""),
            label_hash=str(lin.get("label_hash") or ""),
            processor_version=str(lin.get("processor_version") or ""),
            training_config_hash=str(lin.get("training_config_hash") or ""),
            snapshot_id=str(lin.get("snapshot_id") or ""),
        ),
        metadata=dict(metadata or {}),
    )


def normalize_artifact_type(raw: str | None) -> str:
    t = str(raw or "MODEL").strip().upper()
    if t in ("MODEL_BUNDLE", "MODEL", ""):
        return "MODEL"
    return t


__all__ = [
    "MANIFEST_SCHEMA",
    "ArtifactContentInfo",
    "ArtifactLineageInfo",
    "ArtifactManifest",
    "build_artifact_manifest",
    "normalize_artifact_type",
]
