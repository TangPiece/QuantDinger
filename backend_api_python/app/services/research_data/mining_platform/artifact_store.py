"""MiningRun 索引 + Candidate 本地镜像。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.research_data import config as rd_config

from .identity import candidate_key, mining_run_index_key, mining_score_key


def platform_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "mining_platform"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class MiningArtifactStore:
    root: Path | None = None

    def _rel(self, r2_key: str) -> Path:
        rel = r2_key.split(f"{rd_config.canonical_prefix()}/", 1)[-1]
        return platform_root(self.root) / rel

    def run_index_path(self, *, mining_run_hash: str) -> Path:
        key = mining_run_index_key(mining_run_hash=mining_run_hash)
        return self._rel(key)

    def candidate_path(self, *, mining_run_id: str, candidate_id: str) -> Path:
        key = candidate_key(mining_run_id=mining_run_id, candidate_id=candidate_id)
        return self._rel(key)

    def score_path(self, *, mining_run_id: str, candidate_id: str) -> Path:
        key = mining_score_key(mining_run_id=mining_run_id, candidate_id=candidate_id)
        return self._rel(key)

    def list_run_index_paths(self) -> list[Path]:
        base = platform_root(self.root)
        if not base.is_dir():
            return []
        return sorted(base.glob("**/run_index.json"))


__all__ = ["MiningArtifactStore", "platform_root"]
