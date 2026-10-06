"""Portfolio manifest / summary.json / metrics/summary.json。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import (
    ArtifactRecord,
    FactorPortfolioSummary,
)
from app.services.research_data.paths import (
    factor_portfolio_manifest_key,
    factor_portfolio_metrics_key,
    factor_portfolio_summary_key,
)

from .protocol import PORTFOLIO_VERSION, PortfolioManifest


class PortfolioManifestError(ValueError):
    pass


def portfolio_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "portfolio"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class PortfolioArtifactStore:
    root: Path | None = None

    def dir_for(self, portfolio_hash: str) -> Path:
        return portfolio_root(self.root) / portfolio_hash

    def write_manifest(
        self,
        manifest: PortfolioManifest,
        *,
        summary: FactorPortfolioSummary | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        phash = manifest.portfolio_hash
        if not phash:
            raise PortfolioManifestError("portfolio_hash required")
        dest = self.dir_for(phash)
        dest.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump(mode="json")
        payload.setdefault(
            "r2_key", factor_portfolio_manifest_key(portfolio_hash=phash)
        )
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        (dest / "manifest.json").write_text(text, encoding="utf-8")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if summary is not None:
            summary_payload: dict[str, Any] = {
                "portfolio_hash": phash,
                "portfolio_version": (
                    manifest.portfolio_version or PORTFOLIO_VERSION
                ),
                "summary": summary.model_dump(mode="json"),
                "r2_key": factor_portfolio_summary_key(portfolio_hash=phash),
            }
            (dest / "summary.json").write_text(
                json.dumps(
                    summary_payload, ensure_ascii=False, indent=2, default=str
                ),
                encoding="utf-8",
            )

        if metrics is not None:
            mdir = dest / "metrics"
            mdir.mkdir(parents=True, exist_ok=True)
            metrics_payload = {
                "portfolio_hash": phash,
                "metrics": metrics,
                "r2_key": factor_portfolio_metrics_key(portfolio_hash=phash),
            }
            (mdir / "summary.json").write_text(
                json.dumps(
                    metrics_payload, ensure_ascii=False, indent=2, default=str
                ),
                encoding="utf-8",
            )

        return ArtifactRecord(
            artifact_id=phash,
            artifact_type="factor_portfolio",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=len(text.encode("utf-8")),
            metadata={
                "portfolio_hash": phash,
                "factor_dataset_id": manifest.factor_dataset_id,
            },
        )
