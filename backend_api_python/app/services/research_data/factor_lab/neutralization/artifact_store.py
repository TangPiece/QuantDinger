"""Neutralization manifest / summary.json。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import (
    ArtifactRecord,
    FactorNeutralizationSummary,
)
from app.services.research_data.paths import (
    neutralized_factor_manifest_key,
    neutralized_factor_summary_key,
)

from .protocol import NEUTRALIZATION_VERSION, NeutralizationManifest


class NeutralizationManifestError(ValueError):
    pass


def neutralized_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "factor" / "neutralized"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class NeutralizationArtifactStore:
    root: Path | None = None

    def dir_for(self, neutralization_hash: str) -> Path:
        return neutralized_root(self.root) / neutralization_hash

    def write_manifest(
        self,
        manifest: NeutralizationManifest,
        *,
        summary: FactorNeutralizationSummary | None = None,
    ) -> ArtifactRecord:
        nhash = manifest.neutralization_hash
        if not nhash:
            raise NeutralizationManifestError("neutralization_hash required")
        dest = self.dir_for(nhash)
        dest.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump(mode="json")
        payload.setdefault(
            "r2_key", neutralized_factor_manifest_key(neutralization_hash=nhash)
        )
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        (dest / "manifest.json").write_text(text, encoding="utf-8")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if summary is not None:
            summary_payload: dict[str, Any] = {
                "neutralization_hash": nhash,
                "neutralization_version": (
                    manifest.neutralization_version or NEUTRALIZATION_VERSION
                ),
                "summary": summary.model_dump(mode="json"),
                "r2_key": neutralized_factor_summary_key(neutralization_hash=nhash),
            }
            (dest / "summary.json").write_text(
                json.dumps(summary_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

        return ArtifactRecord(
            artifact_id=nhash,
            artifact_type="factor_neutralization",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=len(text.encode("utf-8")),
            metadata={
                "neutralization_hash": nhash,
                "factor_dataset_id": manifest.factor_dataset_id,
                "neutralized_factor_dataset_id": manifest.neutralized_factor_dataset_id,
            },
        )
