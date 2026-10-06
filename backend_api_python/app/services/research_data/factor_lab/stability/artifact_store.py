"""Stability manifest / summary.json：本地 cache 镜像。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import (
    ArtifactRecord,
    FactorStabilitySummary,
)
from app.services.research_data.paths import (
    evaluation_stability_manifest_key,
    evaluation_stability_summary_key,
)

from .protocol import STABILITY_VERSION, StabilityManifest


class StabilityManifestError(ValueError):
    pass


def stability_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "evaluation" / "stability"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class StabilityArtifactStore:
    root: Path | None = None

    def dir_for(self, stability_hash: str) -> Path:
        return stability_root(self.root) / stability_hash

    def write_manifest(
        self,
        manifest: StabilityManifest,
        *,
        summaries: list[FactorStabilitySummary] | None = None,
    ) -> ArtifactRecord:
        shash = manifest.stability_hash
        if not shash:
            raise StabilityManifestError("stability_hash required")
        dest = self.dir_for(shash)
        dest.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump(mode="json")
        payload.setdefault(
            "r2_key", evaluation_stability_manifest_key(stability_hash=shash)
        )
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        (dest / "manifest.json").write_text(text, encoding="utf-8")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if summaries is not None:
            summary_payload: dict[str, Any] = {
                "stability_hash": shash,
                "evaluation_hash": manifest.evaluation_hash,
                "stability_version": manifest.stability_version or STABILITY_VERSION,
                "summaries": [s.model_dump(mode="json") for s in summaries],
                "r2_key": evaluation_stability_summary_key(stability_hash=shash),
            }
            (dest / "summary.json").write_text(
                json.dumps(summary_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

        return ArtifactRecord(
            artifact_id=shash,
            artifact_type="factor_stability_evaluation",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=len(text.encode("utf-8")),
            metadata={
                "stability_hash": shash,
                "evaluation_hash": manifest.evaluation_hash,
                "factor_dataset_id": manifest.factor_dataset_id,
            },
        )
