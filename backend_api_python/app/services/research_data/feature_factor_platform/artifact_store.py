"""FeatureSet manifest + Build 索引本地镜像。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.research_data import config as rd_config

from .identity import factor_build_index_key, feature_set_r2_key


def platform_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "feature_factor"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class FeatureFactorArtifactStore:
    root: Path | None = None

    def _rel(self, r2_key: str) -> Path:
        rel = r2_key.split(f"{rd_config.canonical_prefix()}/", 1)[-1]
        return platform_root(self.root) / rel

    def feature_set_manifest_path(self, *, code: str, version: str) -> Path:
        return self._rel(feature_set_r2_key(code=code, version=version))

    def factor_build_index_path(
        self,
        *,
        factor_ref: str,
        dataset_hash: str,
        layout: str,
        start_date: str,
        end_date: str,
    ) -> Path:
        key = factor_build_index_key(
            factor_ref=factor_ref,
            dataset_hash=dataset_hash,
            layout=layout,
            start_date=start_date,
            end_date=end_date,
        )
        return self._rel(key)

    def feature_set_build_index_path(
        self,
        *,
        feature_set_ref: str,
        dataset_hash: str,
        layout: str,
        start_date: str,
        end_date: str,
    ) -> Path:
        from .identity import feature_set_build_index_key

        key = feature_set_build_index_key(
            feature_set_ref=feature_set_ref,
            dataset_hash=dataset_hash,
            layout=layout,
            start_date=start_date,
            end_date=end_date,
        )
        return self._rel(key)


__all__ = ["FeatureFactorArtifactStore", "platform_root"]
