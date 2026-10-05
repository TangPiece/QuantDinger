"""模型 Artifact 落盘：本地 research_cache/qd/artifacts/model/{artifact_id}/。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import ArtifactRecord
from app.services.research_data.hashing import canonical_json

from .version import MODEL_TRAINER_VERSION


def compute_config_digest(config: dict[str, Any]) -> str:
    """LGB 超参 canonical 指纹。"""
    payload = canonical_json(config or {})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_model_artifact_id(
    *,
    bundle_hash: str,
    model_ref: str,
    config_digest: str,
    seed: int,
    trainer_version: str = MODEL_TRAINER_VERSION,
) -> str:
    """内容寻址 model artifact 键。"""
    payload = "|".join(
        [
            str(bundle_hash),
            str(model_ref),
            str(config_digest),
            str(seed),
            str(trainer_version),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def model_artifact_root(root: Path | None = None) -> Path:
    """{research_cache}/qd/artifacts/model。"""
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "artifacts" / "model"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class ModelArtifactStore:
    """写入 model.bin / metadata.json / predictions.parquet。"""

    root: Path | None = None

    def dir_for(self, artifact_id: str) -> Path:
        return model_artifact_root(self.root) / artifact_id

    def write_bundle(
        self,
        artifact_id: str,
        *,
        model_bin: bytes,
        metadata: dict[str, Any],
        predictions_parquet: bytes | None = None,
    ) -> ArtifactRecord:
        """原子写入 artifact 目录并返回 Registry 记录。"""
        dest = self.dir_for(artifact_id)
        dest.mkdir(parents=True, exist_ok=True)
        bin_path = dest / "model.bin"
        meta_path = dest / "metadata.json"
        bin_path.write_bytes(model_bin)
        meta_text = json.dumps(metadata, ensure_ascii=False, indent=2)
        meta_path.write_text(meta_text, encoding="utf-8")
        if predictions_parquet is not None:
            (dest / "predictions.parquet").write_bytes(predictions_parquet)

        checksum = hashlib.sha256(model_bin).hexdigest()
        size_bytes = len(model_bin)
        storage_uri = str(dest.resolve())
        return ArtifactRecord(
            artifact_id=artifact_id,
            artifact_type="model",
            storage_uri=storage_uri,
            checksum=checksum,
            size_bytes=size_bytes,
            metadata=metadata,
        )

    def read_metadata(self, artifact_id: str) -> dict[str, Any]:
        path = self.dir_for(artifact_id) / "metadata.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8"))
