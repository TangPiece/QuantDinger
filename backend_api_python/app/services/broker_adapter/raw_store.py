"""Raw Broker Event 落盘：R2/local ``qd/production/broker/...``。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.services.research_data import paths as rd_paths

from .hash import checksum_payload


class BrokerRawStore:
    """写 raw event；Registry 只存索引。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def write_event(
        self,
        *,
        broker_id: str,
        event_id: str,
        payload: Mapping[str, Any],
    ) -> tuple[str, str]:
        """返回 (storage_uri, checksum)。"""
        now = datetime.now(timezone.utc)
        year, month, day = (
            f"{now.year:04d}",
            f"{now.month:02d}",
            f"{now.day:02d}",
        )
        key = rd_paths.production_broker_event_key(
            broker_id=broker_id,
            year=year,
            month=month,
            day=day,
            event_id=event_id,
        )
        raw = dict(payload)
        cs = checksum_payload(raw)
        if self.root is not None:
            path = (
                self.root
                / "production"
                / "broker"
                / broker_id
                / "events"
                / year
                / month
                / day
            )
            path.mkdir(parents=True, exist_ok=True)
            fp = path / f"{event_id}.json"
            fp.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs
