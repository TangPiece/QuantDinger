"""Qlib run manifest / summary / compatibility 本地产物。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import ArtifactRecord, QlibRunSummary
from app.services.research_data.paths import (
    qlib_run_compatibility_key,
    qlib_run_manifest_key,
    qlib_run_metrics_key,
    qlib_run_nav_key,
    qlib_run_summary_key,
)

from .protocol import ENGINE_VERSION, CompatibilityReport, QlibRunManifest


def qlib_run_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "qlib_run"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class QlibRunArtifactStore:
    root: Path | None = None

    def dir_for(self, qlib_run_hash: str) -> Path:
        return qlib_run_root(self.root) / qlib_run_hash

    def write_manifest(
        self,
        manifest: QlibRunManifest,
        *,
        summary: QlibRunSummary | None = None,
        compatibility: CompatibilityReport | None = None,
        metrics: dict[str, Any] | None = None,
        prediction_records: list[dict[str, Any]] | None = None,
        weight_records: list[dict[str, Any]] | None = None,
        nav_curve: list[dict[str, Any]] | None = None,
    ) -> ArtifactRecord:
        rh = manifest.qlib_run_hash
        dest = self.dir_for(rh)
        dest.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump(mode="json")
        payload.setdefault("r2_key", qlib_run_manifest_key(qlib_run_hash=rh))
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        (dest / "manifest.json").write_text(text, encoding="utf-8")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if summary is not None:
            (dest / "summary.json").write_text(
                json.dumps(
                    {
                        "qlib_run_hash": rh,
                        "engine_version": ENGINE_VERSION,
                        "summary": summary.model_dump(mode="json"),
                        "r2_key": qlib_run_summary_key(qlib_run_hash=rh),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        if compatibility is not None:
            (dest / "compatibility.json").write_text(
                json.dumps(
                    {
                        "qlib_run_hash": rh,
                        "compatibility": compatibility.model_dump(mode="json"),
                        "r2_key": qlib_run_compatibility_key(qlib_run_hash=rh),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        if metrics is not None:
            mdir = dest / "metrics"
            mdir.mkdir(parents=True, exist_ok=True)
            (mdir / "summary.json").write_text(
                json.dumps(
                    {
                        "qlib_run_hash": rh,
                        "metrics": metrics,
                        "r2_key": qlib_run_metrics_key(qlib_run_hash=rh),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        if prediction_records is not None:
            pdir = dest / "prediction"
            pdir.mkdir(parents=True, exist_ok=True)
            (pdir / "scores.json").write_text(
                json.dumps(prediction_records, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        if weight_records is not None:
            wdir = dest / "weights"
            wdir.mkdir(parents=True, exist_ok=True)
            (wdir / "weights.json").write_text(
                json.dumps(weight_records, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        # 5E：日频 NAV（与 QD portfolio panel 对齐消费）
        if nav_curve is not None:
            ndir = dest / "nav"
            ndir.mkdir(parents=True, exist_ok=True)
            (ndir / "daily.json").write_text(
                json.dumps(
                    {
                        "qlib_run_hash": rh,
                        "nav_curve": nav_curve,
                        "r2_key": qlib_run_nav_key(qlib_run_hash=rh),
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )

        return ArtifactRecord(
            artifact_id=rh,
            artifact_type="qlib_strategy_run",
            storage_uri=str(dest.resolve()),
            checksum=checksum,
            size_bytes=len(text.encode("utf-8")),
            metadata={"qlib_run_hash": rh, "strategy_hash": manifest.strategy_hash},
        )
