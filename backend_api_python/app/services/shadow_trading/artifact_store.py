"""Phase 7B：Shadow run artifact R2/本地。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.research_data import paths as rd_paths

from .protocol import ShadowCompareReport, ShadowOrder


class ShadowArtifactStore:
    """``qd/production/shadow/{account_id}/yyyy/mm/dd/{run_id}.json``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def write_run_payload(
        self,
        *,
        account_id: str,
        run_id: str,
        payload: dict[str, Any],
    ) -> tuple[str, str]:
        captured = str(payload.get("created_at") or datetime.now(timezone.utc).isoformat())
        try:
            dt = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
        key = rd_paths.production_shadow_run_key(
            account_id=account_id or "unknown",
            yyyy=f"{dt.year:04d}",
            mm=f"{dt.month:02d}",
            dd=f"{dt.day:02d}",
            run_id=run_id,
        )
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        cs = __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/production/shadow/", 1)[-1]
            fp = self.root / "production" / "shadow" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs
