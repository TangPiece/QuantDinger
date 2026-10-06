"""审计/事件/Trace 派生 id。"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any


def derive_trace_id(*, salt: str = "", seed: str = "") -> str:
    """新交易链路 trace；seed 可选用于确定性测试。"""
    if seed:
        raw = f"ops|trace|{seed}|{salt}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return uuid.uuid4().hex[:24]


def derive_audit_event_id(
    *,
    event_type: str,
    trace_id: str = "",
    entity_id: str = "",
    salt: str = "",
) -> str:
    """幂等 audit event_id。"""
    raw = f"ops|audit|{event_type}|{trace_id}|{entity_id}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def derive_alert_id(*, rule_id: str, bucket: str = "", salt: str = "") -> str:
    raw = f"ops|alert|{rule_id}|{bucket}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def derive_incident_id(*, account_id: str, trace_id: str = "", salt: str = "") -> str:
    raw = f"ops|inc|{account_id}|{trace_id}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def derive_health_snapshot_id(*, account_id: str, salt: str = "") -> str:
    raw = f"ops|health|{account_id}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def checksum_payload(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
