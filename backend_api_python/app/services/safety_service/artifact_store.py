"""R2/本地 SafetyEvent 明细。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.services.research_data import paths as rd_paths

from .hash import checksum_payload
from .protocol import SafetyEvent


class SafetyArtifactStore:
    """``qd/production/safety/{scope}/{yyyy}/{mm}/{dd}/{event_id}.json``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def write_event(self, event: SafetyEvent) -> tuple[str, str]:
        now = datetime.now(timezone.utc)
        year, month, day = f"{now.year:04d}", f"{now.month:02d}", f"{now.day:02d}"
        scope = str(event.scope).lower()
        key = rd_paths.production_safety_event_key(
            scope=scope,
            year=year,
            month=month,
            day=day,
            event_id=event.event_id,
        )
        payload = event.model_dump(mode="json")
        cs = checksum_payload(payload)
        if self.root is not None:
            path = (
                self.root
                / "production"
                / "safety"
                / scope
                / year
                / month
                / day
            )
            path.mkdir(parents=True, exist_ok=True)
            fp = path / f"{event.event_id}.json"
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs
