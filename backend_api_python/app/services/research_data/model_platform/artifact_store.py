"""Model Platform 本地镜像路径。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.research_data import config as rd_config

from .identity import (
    model_artifact_key,
    model_key,
    model_version_key,
    training_job_key,
    training_run_key,
)


def platform_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "model_platform"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class ModelArtifactStore:
    root: Path | None = None

    def _rel(self, r2_key: str) -> Path:
        rel = r2_key.split(f"{rd_config.canonical_prefix()}/", 1)[-1]
        return platform_root(self.root) / rel

    def model_path(self, *, model_id: str) -> Path:
        return self._rel(model_key(model_id=model_id))

    def version_path(self, *, model_version_id: str) -> Path:
        return self._rel(model_version_key(model_version_id=model_version_id))

    def training_run_path(self, *, training_run_id: str) -> Path:
        return self._rel(training_run_key(training_run_id=training_run_id))

    def training_job_path(self, *, job_id: str) -> Path:
        return self._rel(training_job_key(job_id=job_id))

    def training_sidecar_dir(self, *, training_run_id: str) -> Path:
        path = platform_root(self.root) / "training_runs" / training_run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def artifact_path(self, *, artifact_id: str) -> Path:
        return self._rel(model_artifact_key(artifact_id=artifact_id))

    def list_model_paths(self) -> list[Path]:
        base = platform_root(self.root) / "models"
        if not base.is_dir():
            return []
        return sorted(base.glob("*.json"))

    def list_version_paths(self) -> list[Path]:
        base = platform_root(self.root) / "versions"
        if not base.is_dir():
            return []
        return sorted(base.glob("*.json"))

    def list_training_run_paths(self) -> list[Path]:
        base = platform_root(self.root) / "training_runs"
        if not base.is_dir():
            return []
        return sorted(p for p in base.glob("*.json") if p.is_file())

    def list_training_job_paths(self) -> list[Path]:
        base = platform_root(self.root) / "training_jobs"
        if not base.is_dir():
            return []
        return sorted(base.glob("*.json"))

    def root_path(self) -> Path:
        return platform_root(self.root)


__all__ = ["ModelArtifactStore", "platform_root"]
