"""Experiment manifest 落盘：qd/artifacts/experiments/{experiment_id}/manifest.json。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import ExperimentManifest


def experiment_artifact_root(root: Path | None = None) -> Path:
    """{research_cache}/qd/artifacts/experiments。"""
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "artifacts" / "experiments"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class ExperimentManifestStore:
    """读写 experiment manifest（快照，非 SSOT）。"""

    root: Path | None = None

    def dir_for(self, experiment_id: str) -> Path:
        return experiment_artifact_root(self.root) / experiment_id

    def write(self, manifest: ExperimentManifest) -> str:
        """写入 manifest.json，返回绝对路径 URI。"""
        dest = self.dir_for(manifest.experiment_id)
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / "manifest.json"
        payload = manifest.model_dump(mode="json")
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return str(path.resolve())

    def read(self, experiment_id: str) -> ExperimentManifest:
        path = self.dir_for(experiment_id) / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ExperimentManifest.model_validate(raw)
