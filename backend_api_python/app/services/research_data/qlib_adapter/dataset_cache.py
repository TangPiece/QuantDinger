"""qlib-dataset-cache：与 Materializer qlib-cache 分离的 Dataset 产物缓存。"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config

from .version import ADAPTER_VERSION


def dataset_cache_root(root: Path | None = None) -> Path:
    """Dataset 产物缓存根。

    - root 为 None：{research_cache}/qlib-dataset-cache
    - root 已显式传入：视为最终缓存根（不再二次拼接目录名）
    """
    if root is not None:
        path = Path(root)
    else:
        path = rd_config.research_cache_dir() / "qlib-dataset-cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def compute_dataset_artifact_id(
    *,
    bundle_hash: str,
    segments: dict[str, Any],
    label: dict[str, Any] | None,
    adapter_version: str = ADAPTER_VERSION,
) -> str:
    """Dataset 产物键：bundle + segments + label + adapter。"""
    payload = "|".join(
        [
            str(bundle_hash),
            json.dumps(segments, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
            json.dumps(label or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
            str(adapter_version),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DatasetArtifactCache:
    """管理 qlib-dataset-cache/{artifact_id}/manifest.json。"""

    def __init__(self, root: Path | None = None) -> None:
        self._root = dataset_cache_root(root)
        self._lock = threading.Lock()

    @property
    def root(self) -> Path:
        return self._root

    def dir_for(self, artifact_id: str) -> Path:
        return self._root / artifact_id

    def is_ready(self, artifact_id: str) -> bool:
        mani = self.read_manifest(artifact_id)
        return bool(mani and mani.get("status") == "READY")

    def read_manifest(self, artifact_id: str) -> dict[str, Any] | None:
        path = self.dir_for(artifact_id) / "manifest.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def write_ready(
        self,
        artifact_id: str,
        *,
        dataset_ref: str,
        dataset_hash: str,
        bundle_hash: str,
        segments: dict[str, Any],
        label: dict[str, Any] | None,
        materialization_id: str,
        qlib_cache_path: str,
        extra: dict[str, Any] | None = None,
    ) -> Path:
        """写入 READY manifest（原子写临时再替换）。"""
        with self._lock:
            dest = self.dir_for(artifact_id)
            dest.mkdir(parents=True, exist_ok=True)
            payload: dict[str, Any] = {
                "status": "READY",
                "artifact_id": artifact_id,
                "dataset_ref": dataset_ref,
                "dataset_hash": dataset_hash,
                "bundle_hash": bundle_hash,
                "adapter_version": ADAPTER_VERSION,
                "segments": segments,
                "label": label,
                "materialization_id": materialization_id,
                "qlib_cache_path": qlib_cache_path,
            }
            if extra:
                payload.update(extra)
            tmp = dest / "manifest.json.tmp"
            final = dest / "manifest.json"
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(final)
            return dest
