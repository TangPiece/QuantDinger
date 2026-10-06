"""R2/本地 BrokerSnapshot 明细存储。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.research_data import paths as rd_paths

from .hash import checksum_payload
from .protocol import BrokerSnapshot


class ReconciliationArtifactStore:
    """写入 ``qd/production/reconciliation/{broker}/{account}/{y}/{m}/{d}/{id}.json``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def write_snapshot(self, snapshot: BrokerSnapshot) -> tuple[str, str]:
        """返回 (storage_uri, checksum)。"""
        captured = snapshot.captured_at or datetime.now(timezone.utc).isoformat()
        day = captured[:10]
        parts = day.split("-")
        year = parts[0] if len(parts) > 0 else "1970"
        month = parts[1] if len(parts) > 1 else "01"
        day_n = parts[2] if len(parts) > 2 else "01"
        broker_id = snapshot.broker_id or "unknown"
        account_id = snapshot.account_id or "unknown"
        key = rd_paths.production_reconciliation_snapshot_key(
            broker_id=broker_id,
            account_id=account_id,
            year=year,
            month=month,
            day=day_n,
            snapshot_id=snapshot.snapshot_id,
        )
        payload = snapshot.model_dump(mode="json")
        cs = checksum_payload(payload)
        if self.root is not None:
            path = (
                self.root
                / "production"
                / "reconciliation"
                / broker_id
                / account_id
                / year
                / month
                / day_n
            )
            path.mkdir(parents=True, exist_ok=True)
            fp = path / f"{snapshot.snapshot_id}.json"
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs
