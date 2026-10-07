"""Phase 7C：Controlled Live run artifact R2/本地。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.research_data import paths as rd_paths


class ControlledLiveArtifactStore:
    """``qd/production/controlled_live/{account_id}/yyyy/mm/dd/{run_id}.json``。"""

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
        key = rd_paths.production_controlled_live_run_key(
            account_id=account_id or "unknown",
            yyyy=f"{dt.year:04d}",
            mm=f"{dt.month:02d}",
            dd=f"{dt.day:02d}",
            run_id=run_id,
        )
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        cs = __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/production/controlled_live/", 1)[-1]
            fp = self.root / "production" / "controlled_live" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs

    def write_runtime_tick_payload(
        self,
        *,
        account_id: str,
        tick_id: str,
        payload: dict[str, Any],
    ) -> tuple[str, str]:
        """``qd/production/controlled_live/{account_id}/runtime/.../{tick_id}.json``。"""
        captured = str(payload.get("as_of") or datetime.now(timezone.utc).isoformat())
        try:
            dt = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
        key = rd_paths.production_controlled_live_runtime_tick_key(
            account_id=account_id or "unknown",
            yyyy=f"{dt.year:04d}",
            mm=f"{dt.month:02d}",
            dd=f"{dt.day:02d}",
            tick_id=tick_id,
        )
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        cs = __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/production/controlled_live/", 1)[-1]
            fp = self.root / "production" / "controlled_live" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs

    def write_drift_daily_payload(
        self,
        *,
        account_id: str,
        trading_date: str,
        run_id: str,
        payload: dict[str, Any],
    ) -> tuple[str, str]:
        key = rd_paths.production_controlled_live_drift_daily_key(
            account_id=account_id or "unknown",
            trading_date=trading_date,
            run_id=run_id,
        )
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        cs = __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()[:40]
        if self.root is not None:
            rel = key.split("/production/controlled_live/", 1)[-1]
            fp = self.root / "production" / "controlled_live" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs
