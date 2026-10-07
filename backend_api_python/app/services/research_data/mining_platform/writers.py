"""写入 MiningRunIndex / Candidate / MiningScore。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .artifact_store import MiningArtifactStore
from .protocol import FactorCandidate, MiningRunIndex, MiningScore


@dataclass
class WriteResult:
    path: str
    checksum: str


def write_run_index(store: MiningArtifactStore, index: MiningRunIndex) -> WriteResult:
    path = store.run_index_path(mining_run_hash=index.mining_run_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(index.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    cs = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return WriteResult(path=str(path.resolve()), checksum=cs)


def write_candidate(store: MiningArtifactStore, candidate: FactorCandidate) -> WriteResult:
    path = store.candidate_path(
        mining_run_id=candidate.mining_run_id,
        candidate_id=candidate.candidate_id,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    cs = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return WriteResult(path=str(path.resolve()), checksum=cs)


def write_mining_score(store: MiningArtifactStore, score: MiningScore) -> WriteResult:
    path = store.score_path(
        mining_run_id=score.mining_run_id,
        candidate_id=score.candidate_id,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(score.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    cs = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return WriteResult(path=str(path.resolve()), checksum=cs)


__all__ = ["WriteResult", "write_candidate", "write_mining_score", "write_run_index"]
