"""Evaluation Manifest：qd/evaluation/factor/{hash}/manifest.json。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import ArtifactRecord, EvaluationDatasetRecord
from app.services.research_data.paths import evaluation_manifest_key

from .protocol import EVALUATOR_VERSION, EvaluationManifest

MANIFEST_REQUIRED = frozenset(
    {
        "evaluation_hash",
        "factor_dataset_id",
        "factor_dataset_hash",
        "snapshot_id",
        "schema_version",
        "min_date",
        "max_date",
        "universe_code",
        "row_count",
        "checksum",
        "evaluator_version",
        "return_spec",
    }
)


class EvaluationManifestError(ValueError):
    """Manifest 非法。"""


def validate_evaluation_manifest(manifest: EvaluationManifest) -> None:
    """校验必填字段。"""
    data = manifest.model_dump(mode="json")
    missing = [k for k in MANIFEST_REQUIRED if data.get(k) in (None, "", [])]
    if missing:
        raise EvaluationManifestError(f"manifest missing: {missing}")


def evaluation_root(root: Path | None = None) -> Path:
    """本地 cache 下 qd/evaluation/factor。"""
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "evaluation" / "factor"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class EvaluationArtifactStore:
    """写入 Evaluation Manifest。"""

    root: Path | None = None

    def dir_for(self, evaluation_hash: str) -> Path:
        return evaluation_root(self.root) / evaluation_hash

    def write_manifest(
        self,
        manifest: EvaluationManifest,
        *,
        record: EvaluationDatasetRecord | None = None,
    ) -> ArtifactRecord:
        """校验并落盘 manifest.json。"""
        validate_evaluation_manifest(manifest)
        ehash = manifest.evaluation_hash or (
            record.evaluation_hash if record else ""
        )
        if not ehash:
            raise EvaluationManifestError("evaluation_hash required")
        dest = self.dir_for(ehash)
        dest.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump(mode="json")
        payload["evaluator_version"] = (
            manifest.evaluator_version or EVALUATOR_VERSION
        )
        payload.setdefault(
            "r2_key", evaluation_manifest_key(evaluation_hash=ehash)
        )
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        path = dest / "manifest.json"
        path.write_text(text, encoding="utf-8")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        uri = str(dest.resolve())
        return ArtifactRecord(
            artifact_id=ehash,
            artifact_type="evaluation_dataset",
            storage_uri=uri,
            checksum=checksum,
            size_bytes=len(text.encode("utf-8")),
            metadata={
                "evaluation_hash": ehash,
                "factor_dataset_id": manifest.factor_dataset_id,
                "factor_dataset_hash": manifest.factor_dataset_hash,
                "snapshot_id": manifest.snapshot_id,
                "universe_code": manifest.universe_code,
                "schema_version": manifest.schema_version,
            },
        )

    def read_manifest(self, evaluation_hash: str) -> EvaluationManifest:
        path = self.dir_for(evaluation_hash) / "manifest.json"
        if not path.is_file():
            raise KeyError(f"evaluation manifest not found: {evaluation_hash}")
        return EvaluationManifest.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
