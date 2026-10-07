"""Phase 8F：metric / health / alert 确定性 ID。"""

from __future__ import annotations

import hashlib
import json
import re

_KEY_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")


class InvalidMonitoringIdentityError(ValueError):
    """非法 monitoring 身份输入。"""


def normalize_session_id(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if not _KEY_RE.match(text):
        raise InvalidMonitoringIdentityError(f"invalid session_id: {raw!r}")
    return text


def build_metric_id(*, strategy_code: str, category: str, name: str, collected_at: str) -> str:
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "category": str(category or "").strip().upper(),
        "name": str(name or "").strip(),
        "collected_at": str(collected_at or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"mon_met_{digest}"


def build_health_snapshot_id(*, strategy_code: str, evaluated_at: str, session_id: str) -> str:
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "evaluated_at": str(evaluated_at or "").strip(),
        "session_id": str(session_id or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"mon_hlt_{digest}"


def build_alert_fingerprint(*, rule_id: str, category: str, metric: str, value: float) -> str:
    payload = {
        "rule_id": str(rule_id or "").strip(),
        "category": str(category or "").strip().upper(),
        "metric": str(metric or "").strip(),
        "value_bucket": round(float(value), 6),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def build_alert_id(*, strategy_code: str, rule_id: str, fingerprint: str) -> str:
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "rule_id": str(rule_id or "").strip(),
        "fingerprint": str(fingerprint or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"mon_alt_{digest}"


def build_dispatch_id(*, alert_id: str, channel: str, dispatched_at: str) -> str:
    payload = {
        "alert_id": str(alert_id or "").strip(),
        "channel": str(channel or "").strip().upper(),
        "dispatched_at": str(dispatched_at or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"mon_nfy_{digest}"


def build_governance_event_id(*, strategy_code: str, alert_id: str, created_at: str) -> str:
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "alert_id": str(alert_id or "").strip(),
        "created_at": str(created_at or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"mon_gov_{digest}"


__all__ = [
    "InvalidMonitoringIdentityError",
    "build_alert_fingerprint",
    "build_alert_id",
    "build_dispatch_id",
    "build_governance_event_id",
    "build_health_snapshot_id",
    "build_metric_id",
    "normalize_session_id",
]
