"""event_id / intent_id / state key 派生。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def scope_key(scope: str, scope_id: str) -> str:
    return f"{scope}|{scope_id or '_'}"


def derive_event_id(
    *,
    rule: str,
    scope: str,
    scope_id: str,
    trigger_bucket: str = "",
    salt: str = "",
) -> str:
    """幂等 event_id：同 rule+scope+bucket 不重复创建。"""
    raw = f"safety|evt|{rule}|{scope}|{scope_id}|{trigger_bucket}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def derive_intent_id(
    *,
    scope: str,
    scope_id: str,
    salt: str = "",
) -> str:
    raw = f"safety|emg|{scope}|{scope_id}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def checksum_payload(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def stable_json(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
