"""def.json + manifest.json 本地镜像（测试 / 离线验收）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.research_data import config as rd_config

from .identity import dataset_definition_key, manifest_r2_key
from app.services.research_data.contracts import DatasetDefinition


def platform_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "dataset"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_segment(text: str) -> str:
    return str(text or "").replace("/", "_")


@dataclass
class DatasetArtifactStore:
    """按 R2 相对路径镜像 dataset 包。"""

    root: Path | None = None

    def def_path(self, definition: DatasetDefinition) -> Path:
        key = dataset_definition_key(
            dataset_code=definition.code, dataset_version=definition.version
        )
        rel = key.split(f"{rd_config.canonical_prefix()}/", 1)[-1]
        return platform_root(self.root) / rel

    def manifest_path(self, definition: DatasetDefinition) -> Path:
        key = manifest_r2_key(definition)
        rel = key.split(f"{rd_config.canonical_prefix()}/", 1)[-1]
        return platform_root(self.root) / rel

    def manifest_dir(self, definition: DatasetDefinition) -> Path:
        return self.manifest_path(definition).parent

    def dataset_dir(self, definition: DatasetDefinition) -> Path:
        """``dataset/{code}/{version}/`` 目录。"""
        base = platform_root(self.root)
        return (
            base
            / _safe_segment(definition.code)
            / _safe_segment(definition.version)
        )


__all__ = ["DatasetArtifactStore", "platform_root"]
