"""Backtest manifest / summary / metrics 本地产物。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import (
    ArtifactRecord,
    ResearchBacktestSummary,
)
from app.services.research_data.paths import (
    research_backtest_manifest_key,
    research_backtest_metrics_key,
    research_backtest_summary_key,
)

from .protocol import ENGINE_VERSION, BacktestManifest


class BacktestManifestError(ValueError):
    pass


def backtest_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "backtest"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class BacktestArtifactStore:
    root: Path | None = None

    def dir_for(self, backtest_hash: str) -> Path:
        return backtest_root(self.root) / backtest_hash

    def write_manifest(
        self,
        manifest: BacktestManifest,
        *,
        summary: ResearchBacktestSummary | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        bhash = manifest.backtest_hash
        if not bhash:
            raise BacktestManifestError("backtest_hash required")
        dest = self.dir_for(bhash)
        dest.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump(mode="json")
        payload.setdefault(
            "r2_key", research_backtest_manifest_key(backtest_hash=bhash)
        )
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        (dest / "manifest.json").write_text(text, encoding="utf-8")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if summary is not None:
            summary_payload = {
                "backtest_hash": bhash,
                "engine_version": manifest.engine_version or ENGINE_VERSION,
                "summary": summary.model_dump(mode="json"),
                "r2_key": research_backtest_summary_key(backtest_hash=bhash),
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
            m_payload = {
                "backtest_hash": bhash,
                "metrics": metrics,
                "r2_key": research_backtest_metrics_key(backtest_hash=bhash),
            }
            (mdir / "summary.json").write_text(
                json.dumps(m_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

        return ArtifactRecord(
            artifact_id=bhash,
            artifact_type="research_backtest",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=len(text.encode("utf-8")),
            metadata={
                "backtest_hash": bhash,
                "strategy_hash": manifest.strategy_hash,
            },
        )
