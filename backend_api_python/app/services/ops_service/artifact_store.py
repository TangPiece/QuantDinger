"""R2/本地 Audit / Incident 大 payload。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.services.research_data import paths as rd_paths

from .hash import checksum_payload
from .protocol import AuditEvent, Incident


class OpsArtifactStore:
    """``qd/production/audit/`` 与 ``qd/production/incidents/``。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else None

    def write_audit_event(self, event: AuditEvent) -> tuple[str, str]:
        now = datetime.now(timezone.utc)
        year, month, day = f"{now.year:04d}", f"{now.month:02d}", f"{now.day:02d}"
        key = rd_paths.production_audit_event_key(
            year=year,
            month=month,
            day=day,
            event_id=event.event_id,
        )
        payload = event.model_dump(mode="json")
        cs = checksum_payload(payload)
        if self.root is not None:
            path = (
                self.root / "production" / "audit" / year / month / day
            )
            path.mkdir(parents=True, exist_ok=True)
            fp = path / f"{event.event_id}.json"
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs

    def write_incident(self, incident: Incident) -> tuple[str, str]:
        key = rd_paths.production_incident_key(incident_id=incident.incident_id)
        payload = incident.model_dump(mode="json")
        cs = checksum_payload(payload)
        if self.root is not None:
            path = self.root / "production" / "incidents"
            path.mkdir(parents=True, exist_ok=True)
            fp = path / f"{incident.incident_id}.json"
            fp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return str(fp), cs
        return rd_paths.r2_uri(key), cs
