"""Phase 8H：反馈数据集 / 快照 / 案例 确定性 ID。"""

from __future__ import annotations

import hashlib
import json
import re

_KEY_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")


class InvalidFeedbackIdentityError(ValueError):
    """非法 feedback 身份输入。"""


def normalize_session_id(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if not _KEY_RE.match(text):
        raise InvalidFeedbackIdentityError(f"invalid session_id: {raw!r}")
    return text


def build_dataset_id(*, strategy_code: str, feedback_type: str, window_start: str, window_end: str) -> str:
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "feedback_type": str(feedback_type or "").strip().upper(),
        "window_start": str(window_start or "").strip(),
        "window_end": str(window_end or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"pfd_{digest}"


def build_snapshot_id(*, strategy_code: str, as_of_time: str) -> str:
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "as_of_time": str(as_of_time or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"pfrs_{digest}"


def build_failure_case_id(*, strategy_code: str, incident_id: str, created_at: str) -> str:
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "incident_id": str(incident_id or "").strip(),
        "created_at": str(created_at or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"rfc_{digest}"


def build_hypothesis_id(*, strategy_code: str, title: str, created_at: str) -> str:
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "title": str(title or "").strip(),
        "created_at": str(created_at or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"rhyp_{digest}"


def build_experiment_link_id(*, experiment_id: str, created_at: str) -> str:
    payload = {
        "experiment_id": str(experiment_id or "").strip(),
        "created_at": str(created_at or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"fel_{digest}"


def build_counterfactual_id(*, parent_snapshot_id: str, scenario_key: str) -> str:
    payload = {
        "parent_snapshot_id": str(parent_snapshot_id or "").strip(),
        "scenario_key": str(scenario_key or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"pfcf_{digest}"


__all__ = [
    "InvalidFeedbackIdentityError",
    "build_counterfactual_id",
    "build_dataset_id",
    "build_experiment_link_id",
    "build_failure_case_id",
    "build_hypothesis_id",
    "build_snapshot_id",
    "normalize_session_id",
]
