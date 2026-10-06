"""Phase 6I：E2E 运行明细 R2/本地存储。"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.research_data import paths as rd_paths

from .hash import intent_fingerprint
from .protocol import E2ERunPayload, ScenarioResult


class E2EArtifactStore:
    """``qd/production/e2e/{session_id}/{run_id}.json``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def write_run_payload(
        self,
        payload: E2ERunPayload,
        *,
        session_id: str,
        run_id: str,
    ) -> tuple[str, str]:
        key = rd_paths.production_e2e_run_key(session_id=session_id, run_id=run_id)
        body = payload.model_dump(mode="json")
        cs = intent_fingerprint([body])
        if self.root is not None:
            path = self.root / "production" / "e2e" / session_id
            path.mkdir(parents=True, exist_ok=True)
            fp = path / f"{run_id}.json"
            fp.write_text(
                json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs

    def read_scenario_summary(self, result: ScenarioResult) -> dict:
        return result.model_dump(mode="json")
