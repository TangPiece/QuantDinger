"""写入 EvaluationRunIndex 与 QualityScore。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from .artifact_store import EvaluationArtifactStore
from .protocol import EvaluationRunIndex, FactorQualityScore


@dataclass
class WriteResult:
    path: str
    checksum: str


def write_run_index(
    store: EvaluationArtifactStore,
    index: EvaluationRunIndex,
) -> WriteResult:
    path = store.run_index_path(run_content_hash=index.run_content_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(index.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    cs = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return WriteResult(path=str(path.resolve()), checksum=cs)


def write_quality_score(
    store: EvaluationArtifactStore,
    score: FactorQualityScore,
) -> WriteResult:
    path = store.quality_score_path(evaluation_id=score.evaluation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(score.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    cs = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return WriteResult(path=str(path.resolve()), checksum=cs)


def iso_ts(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = ["WriteResult", "write_quality_score", "write_run_index", "iso_ts"]
