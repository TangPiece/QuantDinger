"""RuntimeEvent append / query。"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.research_data.contracts import ProductionRuntimeEventRecord

from .protocol import EventType


def make_event_id(runtime_id: str, event_type: str, *, salt: str = "") -> str:
    raw = f"{runtime_id}|{event_type}|{salt or uuid.uuid4().hex}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def append_event(
    registry: Any,
    *,
    runtime_id: str,
    event_type: EventType | str,
    trading_date: str = "",
    session_phase: str = "",
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> ProductionRuntimeEventRecord:
    """写一条 RuntimeEvent；registry 无方法时仅返回记录。"""
    rec = ProductionRuntimeEventRecord(
        event_id=make_event_id(runtime_id, str(event_type)),
        runtime_id=runtime_id,
        event_type=str(event_type),
        trading_date=trading_date,
        session_phase=session_phase,
        message=message,
        payload_json=dict(payload or {}),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    writer = getattr(registry, "append_runtime_event", None)
    if writer is not None:
        try:
            writer(rec)
        except Exception:
            pass
    return rec


def list_events(
    registry: Any, runtime_id: str, *, limit: int = 200
) -> list[ProductionRuntimeEventRecord]:
    getter = getattr(registry, "list_runtime_events", None)
    if getter is None:
        return []
    try:
        return list(getter(runtime_id, limit=limit) or [])
    except Exception:
        return []
