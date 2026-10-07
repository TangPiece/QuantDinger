"""Reproducibility 本地索引与 Bundle 路径。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.research_data import config as rd_config

from .identity import (
    repro_manifest_key,
    reproducibility_bundle_prefix,
    reproducibility_run_key,
)


def cache_base(root: Path | None = None) -> Path:
    return Path(root) if root is not None else rd_config.research_cache_dir()


def platform_root(root: Path | None = None) -> Path:
    path = cache_base(root) / rd_config.canonical_prefix() / "model_reproducibility"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class ReproducibilityArtifactStore:
    root: Path | None = None

    def _rel(self, r2_key: str) -> Path:
        rel = r2_key.split(f"{rd_config.canonical_prefix()}/", 1)[-1]
        parts = rel.split("/", 1)
        if parts and parts[0] == "model_reproducibility" and len(parts) > 1:
            return platform_root(self.root) / parts[1]
        return platform_root(self.root) / rel

    def manifest_path(self, *, repro_manifest_id: str) -> Path:
        return self._rel(repro_manifest_key(repro_manifest_id=repro_manifest_id))

    def run_path(self, *, reproducibility_run_id: str) -> Path:
        return self._rel(
            reproducibility_run_key(reproducibility_run_id=reproducibility_run_id)
        )

    def bundle_dir(self, *, reproducibility_run_id: str) -> Path:
        key = reproducibility_bundle_prefix(
            reproducibility_run_id=reproducibility_run_id
        )
        rel = key.split(f"{rd_config.canonical_prefix()}/", 1)[-1]
        path = cache_base(self.root) / rd_config.canonical_prefix() / rel
        path.mkdir(parents=True, exist_ok=True)
        return path

    def list_manifest_paths(self) -> list[Path]:
        base = platform_root(self.root) / "manifests"
        if not base.is_dir():
            return []
        return sorted(base.glob("*.json"))

    def list_run_paths(self) -> list[Path]:
        base = platform_root(self.root) / "runs"
        if not base.is_dir():
            return []
        return sorted(base.glob("*.json"))


__all__ = ["ReproducibilityArtifactStore", "cache_base", "platform_root"]
