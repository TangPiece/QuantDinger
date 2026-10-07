"""EvaluationRun 索引 + QualityScore 本地镜像。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.research_data import config as rd_config

from .identity import evaluation_run_index_key, quality_score_key


def platform_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "evaluation_platform"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class EvaluationArtifactStore:
    root: Path | None = None

    def _rel(self, r2_key: str) -> Path:
        rel = r2_key.split(f"{rd_config.canonical_prefix()}/", 1)[-1]
        return platform_root(self.root) / rel

    def run_index_path(self, *, run_content_hash: str) -> Path:
        key = evaluation_run_index_key(run_content_hash=run_content_hash)
        return self._rel(key)

    def quality_score_path(self, *, evaluation_id: str) -> Path:
        key = quality_score_key(evaluation_id=evaluation_id)
        return self._rel(key)

    def list_run_index_paths(self) -> list[Path]:
        base = platform_root(self.root)
        if not base.is_dir():
            return []
        return sorted(base.glob("**/run_index.json"))


__all__ = ["EvaluationArtifactStore", "platform_root"]
