"""写 Manifest / Run 索引与 Bundle 文件。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .artifact_store import ReproducibilityArtifactStore
from .protocol import ReproducibilityManifest, ReproducibilityRun


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def write_manifest(
    store: ReproducibilityArtifactStore, manifest: ReproducibilityManifest
) -> Path:
    path = store.manifest_path(repro_manifest_id=manifest.repro_manifest_id)
    return _write_json(path, manifest.model_dump(mode="json"))


def write_run(store: ReproducibilityArtifactStore, run: ReproducibilityRun) -> Path:
    path = store.run_path(reproducibility_run_id=run.reproducibility_run_id)
    return _write_json(path, run.model_dump(mode="json"))


def write_repro_bundle(
    store: ReproducibilityArtifactStore,
    reproducibility_run_id: str,
    *,
    manifest: Mapping[str, Any] | None = None,
    input_manifest: Mapping[str, Any] | None = None,
    environment: Mapping[str, Any] | None = None,
    dependency_lock: Mapping[str, Any] | None = None,
    seeds: Mapping[str, Any] | None = None,
    metrics_original: Mapping[str, Any] | None = None,
    metrics_reproduced: Mapping[str, Any] | None = None,
    prediction_diff: Mapping[str, Any] | list[Any] | None = None,
    artifact_comparison: Mapping[str, Any] | None = None,
    report: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    dest = store.bundle_dir(reproducibility_run_id=reproducibility_run_id)
    uris: dict[str, str] = {}
    files = {
        "manifest.json": manifest,
        "input_manifest.json": input_manifest,
        "environment.json": environment,
        "dependency_lock.json": dependency_lock,
        "seeds.json": seeds,
        "metrics_original.json": metrics_original,
        "metrics_reproduced.json": metrics_reproduced,
        "prediction_diff.json": prediction_diff,
        "artifact_comparison.json": artifact_comparison,
        "reproducibility_report.json": report,
    }
    for name, payload in files.items():
        if payload is None:
            continue
        p = dest / name
        if isinstance(payload, list):
            p.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            _write_json(p, dict(payload))
        uris[name.replace(".json", "_uri")] = str(p.resolve())
    return uris


__all__ = ["write_manifest", "write_repro_bundle", "write_run"]
