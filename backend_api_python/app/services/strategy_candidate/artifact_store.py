"""Phase 8B：Candidate manifest（R2 / 本地）。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.services.research_data import paths as rd_paths

from .protocol import StrategyCandidateRecord


class StrategyCandidateArtifactStore:
    """``qd/registry/candidates/{candidate_id}/manifest.json``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def write_manifest(self, record: StrategyCandidateRecord) -> tuple[str, str]:
        """写入 manifest；返回 (storage_uri, checksum)。"""
        key = rd_paths.strategy_candidate_manifest_key(candidate_id=record.candidate_id)
        payload: dict[str, Any] = record.model_dump(mode="json")
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        cs = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/registry/candidates/", 1)[-1]
            fp = self.root / "registry" / "candidates" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs


__all__ = ["StrategyCandidateArtifactStore"]
