"""Phase 7B：Live MD 事件 batch R2/本地存储。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from app.services.research_data import paths as rd_paths

from .protocol import MarketEvent


class LiveMdArtifactStore:
    """``qd/production/live_md/{feed}/{yyyy}/{mm}/{dd}/{batch_id}.json``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def write_event_batch(
        self,
        *,
        feed_id: str,
        batch_id: str,
        events: Sequence[MarketEvent | dict[str, Any]],
        captured_at: str | None = None,
    ) -> tuple[str, str]:
        captured = captured_at or datetime.now(timezone.utc).isoformat()
        try:
            dt = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
        key = rd_paths.production_live_md_event_batch_key(
            feed_id=feed_id or "default",
            yyyy=f"{dt.year:04d}",
            mm=f"{dt.month:02d}",
            dd=f"{dt.day:02d}",
            event_batch_id=batch_id,
        )
        payload = {
            "batch_id": batch_id,
            "feed_id": feed_id,
            "captured_at": captured,
            "events": [
                e.model_dump(mode="json") if isinstance(e, MarketEvent) else dict(e)
                for e in events
            ],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        cs = __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/production/live_md/", 1)[-1]
            fp = self.root / "production" / "live_md" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs
