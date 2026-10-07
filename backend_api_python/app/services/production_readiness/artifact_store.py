"""Phase 6J：readiness checklist R2/本地存储。"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.research_data import paths as rd_paths

from .protocol import ChecklistResult


class ReadinessArtifactStore:
    """``qd/production/readiness/{run_id}.json``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def write_checklist(self, result: ChecklistResult) -> tuple[str, str]:
        key = rd_paths.production_readiness_run_key(run_id=result.run_id)
        body = result.model_dump(mode="json")
        raw = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        cs = __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            path = self.root / "production" / "readiness"
            path.mkdir(parents=True, exist_ok=True)
            fp = path / f"{result.run_id}.json"
            fp.write_text(
                json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs
