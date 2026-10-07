"""Phase 7A：Live Readonly snapshot R2/本地存储。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.services.reconciliation_service.protocol import BrokerSnapshot
from app.services.research_data import paths as rd_paths


class LiveReadonlyArtifactStore:
    """``qd/production/live_readonly/{account_id}/yyyy/mm/dd/{snapshot_id}.json``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def write_snapshot(self, snapshot: BrokerSnapshot) -> tuple[str, str]:
        captured = snapshot.captured_at or datetime.now(timezone.utc).isoformat()
        try:
            dt = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
        key = rd_paths.production_live_readonly_snapshot_key(
            account_id=snapshot.account_id or "unknown",
            yyyy=f"{dt.year:04d}",
            mm=f"{dt.month:02d}",
            dd=f"{dt.day:02d}",
            snapshot_id=snapshot.snapshot_id,
        )
        body = snapshot.model_dump(mode="json")
        raw = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        cs = __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/production/live_readonly/", 1)[-1]
            fp = self.root / "production" / "live_readonly" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs
