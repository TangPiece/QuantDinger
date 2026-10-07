"""Phase 8G：incident / decision / event 确定性 ID。"""

from __future__ import annotations

import hashlib
import json
import re

_KEY_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")


class InvalidGuardrailIdentityError(ValueError):
    """非法 guardrail 身份输入。"""


def normalize_session_id(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if not _KEY_RE.match(text):
        raise InvalidGuardrailIdentityError(f"invalid session_id: {raw!r}")
    return text


def build_incident_id(*, strategy_code: str, category: str, opened_at: str) -> str:
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "category": str(category or "").strip().upper(),
        "opened_at": str(opened_at or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"gr_inc_{digest}"


def build_decision_id(*, strategy_code: str, decision_type: str, submitted_at: str) -> str:
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "decision_type": str(decision_type or "").strip().upper(),
        "submitted_at": str(submitted_at or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"gr_dec_{digest}"


def build_governance_event_id(*, strategy_code: str, event_type: str, created_at: str) -> str:
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "event_type": str(event_type or "").strip().upper(),
        "created_at": str(created_at or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"gr_evt_{digest}"


def build_rollback_id(*, strategy_code: str, to_version: str, created_at: str) -> str:
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "to_version": str(to_version or "").strip(),
        "created_at": str(created_at or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"gr_rb_{digest}"


__all__ = [
    "InvalidGuardrailIdentityError",
    "build_decision_id",
    "build_governance_event_id",
    "build_incident_id",
    "build_rollback_id",
    "normalize_session_id",
]
