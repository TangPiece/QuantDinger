"""ModelVersion reproducibility manifest。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .protocol import ModelArtifact, ModelVersion, TrainingRun


def build_repro_manifest(
    version: ModelVersion,
    *,
    training_run: TrainingRun | None = None,
    artifact: ModelArtifact | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "model_repro_manifest@1",
        "model_version_id": version.model_version_id,
        "model_code": version.model_code,
        "version": version.version,
        "version_content_hash": version.version_content_hash,
        "dataset_hash": version.dataset_hash,
        "snapshot_id": version.snapshot_id,
        "feature_set_id": version.feature_set_id,
        "feature_set_hash": version.feature_set_hash,
        "factor_portfolio_id": version.factor_portfolio_id,
        "factor_portfolio_version": version.factor_portfolio_version,
        "factor_portfolio_hash": (version.metadata or {}).get(
            "factor_portfolio_hash",
            training_run.factor_portfolio_hash if training_run else "",
        ),
        "label_id": version.label_id,
        "label_hash": version.label_hash,
        "processor_version": version.processor_version,
        "model_config_hash": version.model_config_hash,
        "hyperparameter_hash": version.hyperparameter_hash,
        "framework": version.framework,
        "framework_version": version.framework_version,
        "code_version": version.code_version,
        "environment_hash": version.environment_hash,
        "random_seed": version.random_seed,
        "training_run_id": version.training_run_id,
        "artifact_id": version.artifact_id,
        "artifact_checksum": artifact.checksum if artifact else "",
    }


def repro_manifest_path(store_root: Path, *, model_version_id: str) -> Path:
    return store_root / "versions" / model_version_id / "model_repro_manifest.json"


def write_repro_manifest(
    store_root: Path,
    version: ModelVersion,
    *,
    training_run: TrainingRun | None = None,
    artifact: ModelArtifact | None = None,
) -> Path:
    path = repro_manifest_path(store_root, model_version_id=version.model_version_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_repro_manifest(
        version, training_run=training_run, artifact=artifact
    )
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def load_repro_manifest(store_root: Path, *, model_version_id: str) -> dict[str, Any] | None:
    path = repro_manifest_path(store_root, model_version_id=model_version_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "build_repro_manifest",
    "load_repro_manifest",
    "repro_manifest_path",
    "write_repro_manifest",
]
