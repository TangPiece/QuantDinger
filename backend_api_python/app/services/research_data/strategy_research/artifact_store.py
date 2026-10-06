"""Strategy manifest / summary / snapshots。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import (
    ArtifactRecord,
    StrategyResearchSummary,
)
from app.services.research_data.paths import (
    strategy_research_manifest_key,
    strategy_research_snapshot_key,
    strategy_research_summary_key,
)

from .protocol import STRATEGY_VERSION, StrategyManifest


class StrategyManifestError(ValueError):
    pass


def strategy_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "strategy"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class StrategyArtifactStore:
    root: Path | None = None

    def dir_for(self, strategy_hash: str) -> Path:
        return strategy_root(self.root) / strategy_hash

    def write_manifest(
        self,
        manifest: StrategyManifest,
        *,
        summary: StrategyResearchSummary | None = None,
        strategy_spec: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        shash = manifest.strategy_hash
        if not shash:
            raise StrategyManifestError("strategy_hash required")
        dest = self.dir_for(shash)
        dest.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump(mode="json")
        payload.setdefault(
            "r2_key", strategy_research_manifest_key(strategy_hash=shash)
        )
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        (dest / "manifest.json").write_text(text, encoding="utf-8")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if summary is not None:
            summary_payload = {
                "strategy_hash": shash,
                "strategy_version": (
                    manifest.strategy_version or STRATEGY_VERSION
                ),
                "summary": summary.model_dump(mode="json"),
                "r2_key": strategy_research_summary_key(strategy_hash=shash),
            }
            (dest / "summary.json").write_text(
                json.dumps(
                    summary_payload, ensure_ascii=False, indent=2, default=str
                ),
                encoding="utf-8",
            )

        if strategy_spec is not None:
            snap = dest / "snapshots"
            snap.mkdir(parents=True, exist_ok=True)
            snap_payload = {
                "strategy_hash": shash,
                "strategy_spec": strategy_spec,
                "r2_key": strategy_research_snapshot_key(strategy_hash=shash),
            }
            (snap / "strategy_spec.json").write_text(
                json.dumps(
                    snap_payload, ensure_ascii=False, indent=2, default=str
                ),
                encoding="utf-8",
            )

        return ArtifactRecord(
            artifact_id=shash,
            artifact_type="strategy_research",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=len(text.encode("utf-8")),
            metadata={
                "strategy_hash": shash,
                "strategy_code": manifest.strategy_code,
            },
        )
