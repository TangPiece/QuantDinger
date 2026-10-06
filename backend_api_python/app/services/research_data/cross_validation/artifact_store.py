"""Cross Validation 本地产物。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import ArtifactRecord, CrossValidationSummary
from app.services.research_data.paths import (
    cross_validation_attribution_key,
    cross_validation_manifest_key,
    cross_validation_report_key,
)

from .protocol import CrossValidationManifest, CrossValidationReport, ENGINE_VERSION


def cv_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "cross_validation"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class CrossValidationArtifactStore:
    """写 report / layers / attribution / manifest。"""

    root: Path | None = None

    def dir_for(self, cv_hash: str) -> Path:
        return cv_root(self.root) / cv_hash

    def write_manifest(
        self,
        manifest: CrossValidationManifest,
        *,
        summary: CrossValidationSummary | None = None,
        report: CrossValidationReport | None = None,
    ) -> ArtifactRecord:
        ch = manifest.cv_hash
        dest = self.dir_for(ch)
        dest.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump(mode="json")
        payload.setdefault("r2_key", cross_validation_manifest_key(cv_hash=ch))
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        (dest / "manifest.json").write_text(text, encoding="utf-8")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if summary is not None:
            (dest / "summary.json").write_text(
                json.dumps(
                    {
                        "cv_hash": ch,
                        "engine_version": ENGINE_VERSION,
                        "summary": summary.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        if report is not None:
            (dest / "report.json").write_text(
                json.dumps(
                    {
                        "cv_hash": ch,
                        "report": report.model_dump(mode="json"),
                        "r2_key": cross_validation_report_key(cv_hash=ch),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
            ldir = dest / "layers"
            ldir.mkdir(parents=True, exist_ok=True)
            for layer in report.layers:
                (ldir / f"{layer.layer}.json").write_text(
                    json.dumps(
                        layer.model_dump(mode="json"),
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                    encoding="utf-8",
                )
            (dest / "attribution.json").write_text(
                json.dumps(
                    {
                        "cv_hash": ch,
                        "attribution": report.attribution.model_dump(mode="json"),
                        "r2_key": cross_validation_attribution_key(cv_hash=ch),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
            # NAV day rows（若有）
            nav_layer = next((L for L in report.layers if L.layer == "nav"), None)
            if nav_layer and nav_layer.details.get("days"):
                (dest / "nav_diff.json").write_text(
                    json.dumps(
                        nav_layer.details.get("days"),
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                    encoding="utf-8",
                )

        return ArtifactRecord(
            artifact_id=ch,
            artifact_type="cross_validation",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=len(text.encode("utf-8")),
            metadata={
                "cv_hash": ch,
                "strategy_hash": manifest.strategy_hash,
            },
        )
