"""Metrics Manifest / summary.json：qd/evaluation/metrics/{hash}/。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.research_data import config as rd_config
from app.services.research_data.contracts import (
    ArtifactRecord,
    FactorEvaluationSummary,
)
from app.services.research_data.paths import (
    evaluation_metrics_manifest_key,
    evaluation_metrics_summary_key,
)

from .protocol import (
    CALCULATOR_VERSION,
    METRIC_VERSION,
    MetricManifest,
)

MANIFEST_REQUIRED = frozenset(
    {
        "metric_hash",
        "evaluation_hash",
        "schema_version",
        "checksum",
        "metric_version",
        "calculator_version",
        "row_count",
    }
)


class MetricManifestError(ValueError):
    """Manifest 非法。"""


def validate_metric_manifest(manifest: MetricManifest) -> None:
    data = manifest.model_dump(mode="json")
    missing = [k for k in MANIFEST_REQUIRED if data.get(k) in (None, "")]
    if missing:
        raise MetricManifestError(f"manifest missing: {missing}")


def metrics_root(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else rd_config.research_cache_dir()
    path = base / rd_config.canonical_prefix() / "evaluation" / "metrics"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class MetricArtifactStore:
    """写入 metrics manifest + summary.json。"""

    root: Path | None = None

    def dir_for(self, metric_hash: str) -> Path:
        return metrics_root(self.root) / metric_hash

    def write_manifest(
        self,
        manifest: MetricManifest,
        *,
        summaries: list[FactorEvaluationSummary] | None = None,
    ) -> ArtifactRecord:
        """校验并落盘 manifest.json；可选写 summary.json。"""
        validate_metric_manifest(manifest)
        mhash = manifest.metric_hash
        dest = self.dir_for(mhash)
        dest.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump(mode="json")
        payload.setdefault(
            "r2_key", evaluation_metrics_manifest_key(metric_hash=mhash)
        )
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        (dest / "manifest.json").write_text(text, encoding="utf-8")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if summaries is not None:
            summary_payload: dict[str, Any] = {
                "metric_hash": mhash,
                "evaluation_hash": manifest.evaluation_hash,
                "metric_version": manifest.metric_version or METRIC_VERSION,
                "calculator_version": manifest.calculator_version
                or CALCULATOR_VERSION,
                "summaries": [s.model_dump(mode="json") for s in summaries],
                "r2_key": evaluation_metrics_summary_key(metric_hash=mhash),
            }
            (dest / "summary.json").write_text(
                json.dumps(summary_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

        uri = str(dest.resolve())
        return ArtifactRecord(
            artifact_id=mhash,
            artifact_type="factor_evaluation_metrics",
            storage_uri=uri,
            checksum=checksum,
            size_bytes=len(text.encode("utf-8")),
            metadata={
                "metric_hash": mhash,
                "evaluation_hash": manifest.evaluation_hash,
                "factor_dataset_id": manifest.factor_dataset_id,
                "schema_version": manifest.schema_version,
            },
        )

    def read_manifest(self, metric_hash: str) -> MetricManifest:
        path = self.dir_for(metric_hash) / "manifest.json"
        if not path.is_file():
            raise KeyError(f"metric manifest not found: {metric_hash}")
        return MetricManifest.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
