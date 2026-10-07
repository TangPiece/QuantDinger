"""写入 Model / ModelVersion / TrainingRun / Artifact。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .artifact_store import ModelArtifactStore
from .protocol import Model, ModelArtifact, ModelVersion, TrainingRun


@dataclass
class WriteResult:
    path: str
    checksum: str


def _write_json(path, model) -> WriteResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    cs = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return WriteResult(path=str(path.resolve()), checksum=cs)


def write_model(store: ModelArtifactStore, model: Model) -> WriteResult:
    return _write_json(store.model_path(model_id=model.model_id), model)


def write_version(store: ModelArtifactStore, version: ModelVersion) -> WriteResult:
    return _write_json(store.version_path(model_version_id=version.model_version_id), version)


def write_training_run(store: ModelArtifactStore, run: TrainingRun) -> WriteResult:
    return _write_json(store.training_run_path(training_run_id=run.training_run_id), run)


def write_artifact(store: ModelArtifactStore, artifact: ModelArtifact) -> WriteResult:
    return _write_json(store.artifact_path(artifact_id=artifact.artifact_id), artifact)


__all__ = [
    "WriteResult",
    "write_artifact",
    "write_model",
    "write_training_run",
    "write_version",
]
