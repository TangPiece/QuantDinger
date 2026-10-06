"""session_id / event_id / dedup key。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def derive_session_id(broker_id: str, *, salt: str = "") -> str:
    raw = f"broker|session|{broker_id}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def compute_broker_event_id(
    broker_id: str, broker_execution_id: str, *, salt: str = ""
) -> str:
    raw = f"{broker_id}|{broker_execution_id}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def dedup_key(broker_id: str, broker_execution_id: str) -> str:
    return f"{broker_id}|{broker_execution_id}"


def stable_json(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def checksum_payload(obj: Any) -> str:
    return hashlib.sha256(stable_json(obj).encode("utf-8")).hexdigest()[:40]
