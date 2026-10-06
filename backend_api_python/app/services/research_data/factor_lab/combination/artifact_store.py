"""Combination manifest / summary.json。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import (
    ArtifactRecord,
    FactorCombinationSummary,
)
from app.services.research_data.paths import (
    combined_factor_manifest_key,
    combined_factor_summary_key,
)

from .protocol import COMBINATION_VERSION, CombinationManifest


class CombinationManifestError(ValueError):
    pass


def combined_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "factor" / "combined"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class CombinationArtifactStore:
    root: Path | None = None

    def dir_for(self, combination_hash: str) -> Path:
        return combined_root(self.root) / combination_hash

    def write_manifest(
        self,
        manifest: CombinationManifest,
        *,
        summary: FactorCombinationSummary | None = None,
    ) -> ArtifactRecord:
        chash = manifest.combination_hash
        if not chash:
            raise CombinationManifestError("combination_hash required")
        dest = self.dir_for(chash)
        dest.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump(mode="json")
        payload.setdefault(
            "r2_key", combined_factor_manifest_key(combination_hash=chash)
        )
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        (dest / "manifest.json").write_text(text, encoding="utf-8")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if summary is not None:
            summary_payload: dict[str, Any] = {
                "combination_hash": chash,
                "combination_version": (
                    manifest.combination_version or COMBINATION_VERSION
                ),
                "summary": summary.model_dump(mode="json"),
                "r2_key": combined_factor_summary_key(combination_hash=chash),
            }
            (dest / "summary.json").write_text(
                json.dumps(summary_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

        return ArtifactRecord(
            artifact_id=chash,
            artifact_type="factor_combination",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=len(text.encode("utf-8")),
            metadata={
                "combination_hash": chash,
                "composite_factor_dataset_id": manifest.composite_factor_dataset_id,
            },
        )
