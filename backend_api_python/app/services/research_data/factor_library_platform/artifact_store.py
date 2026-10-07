"""Factor Library 本地镜像路径。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.research_data import config as rd_config

from .identity import cluster_key, collection_key, library_entry_key, portfolio_spec_key


def platform_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "factor_library_platform"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class LibraryArtifactStore:
    root: Path | None = None

    def _rel(self, r2_key: str) -> Path:
        rel = r2_key.split(f"{rd_config.canonical_prefix()}/", 1)[-1]
        return platform_root(self.root) / rel

    def entry_path(self, *, entry_id: str) -> Path:
        return self._rel(library_entry_key(entry_id=entry_id))

    def collection_path(self, *, collection_id: str) -> Path:
        return self._rel(collection_key(collection_id=collection_id))

    def portfolio_path(self, *, portfolio_id: str) -> Path:
        return self._rel(portfolio_spec_key(portfolio_id=portfolio_id))

    def cluster_path(self, *, cluster_id: str) -> Path:
        return self._rel(cluster_key(cluster_id=cluster_id))

    def list_entry_paths(self) -> list[Path]:
        base = platform_root(self.root) / "entries"
        if not base.is_dir():
            return []
        return sorted(base.glob("*.json"))


__all__ = ["LibraryArtifactStore", "platform_root"]
