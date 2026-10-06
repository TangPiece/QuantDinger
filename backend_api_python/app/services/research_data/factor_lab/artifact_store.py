"""Factor Dataset Manifest 落盘：qd/dataset/factor/{id}/manifest.json。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import ArtifactRecord, FactorDatasetRecord
from app.services.research_data.paths import factor_dataset_manifest_key

from .dataset import validate_manifest
from .models import FactorDatasetManifest
from .version import FACTOR_LAB_CONTRACT_VERSION


def factor_dataset_root(root: Path | None = None) -> Path:
    """本地 cache 下 qd/dataset/factor。"""
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "dataset" / "factor"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class FactorDatasetArtifactStore:
    """写入 Factor Dataset Manifest（4A 不写海量值）。"""

    root: Path | None = None

    def dir_for(self, factor_dataset_id: str) -> Path:
        return factor_dataset_root(self.root) / factor_dataset_id

    def write_manifest(
        self,
        manifest: FactorDatasetManifest,
        *,
        record: FactorDatasetRecord | None = None,
    ) -> ArtifactRecord:
        """校验并落盘 manifest.json，返回 ArtifactRecord。"""
        validate_manifest(manifest)
        fid = manifest.factor_dataset_id or (
            record.factor_dataset_id if record else ""
        )
        if not fid:
            raise ValueError("factor_dataset_id required")
        dest = self.dir_for(fid)
        dest.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump(mode="json")
        payload["contract_version"] = FACTOR_LAB_CONTRACT_VERSION
        # 逻辑 R2 key（便于对照）
        payload.setdefault(
            "r2_key",
            factor_dataset_manifest_key(factor_dataset_id=fid),
        )
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        path = dest / "manifest.json"
        path.write_text(text, encoding="utf-8")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        uri = str(dest.resolve())
        return ArtifactRecord(
            artifact_id=fid,
            artifact_type="factor_dataset",
            storage_uri=uri,
            checksum=checksum,
            size_bytes=len(text.encode("utf-8")),
            metadata={
                "factor_ref": f"{manifest.factor_code}@{manifest.factor_version}",
                "factor_hash": manifest.factor_hash,
                "dataset_hash": manifest.dataset_hash,
                "snapshot_id": manifest.snapshot_id,
                "layout": manifest.layout,
                "schema_version": manifest.schema_version,
            },
        )
