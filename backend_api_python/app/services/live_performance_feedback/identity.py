"""Phase 8E：baseline_id / comparison_run_id 确定性构造。"""

from __future__ import annotations

import hashlib
import json
import re

_KEY_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")


class InvalidFeedbackIdentityError(ValueError):
    """非法 idempotency / baseline 输入。"""


def normalize_idempotency_key(raw: str) -> str:
    text = str(raw or "").strip()
    if not text or not _KEY_RE.match(text):
        raise InvalidFeedbackIdentityError(f"invalid idempotency_key: {raw!r}")
    return text


def build_baseline_id(*, pipeline_run_id: str) -> str:
    """同一 promotion run → 同一 baseline_id（freeze 幂等）。"""
    pid = str(pipeline_run_id or "").strip()
    if not pid:
        raise InvalidFeedbackIdentityError("pipeline_run_id required")
    digest = hashlib.sha256(pid.encode("utf-8")).hexdigest()[:24]
    return f"perf_base_{digest}"


def build_comparison_run_id(
    *,
    baseline_id: str,
    actual_source: str,
    window_start: str,
    window_end: str,
    idempotency_key: str,
) -> str:
    """同 window + baseline + source → 同一 comparison run（幂等）。"""
    payload = {
        "baseline_id": str(baseline_id or "").strip(),
        "actual_source": str(actual_source or "").strip().upper(),
        "window_start": str(window_start or "").strip(),
        "window_end": str(window_end or "").strip(),
        "idempotency_key": normalize_idempotency_key(idempotency_key),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"perf_cmp_{digest}"


def build_report_id(*, run_id: str) -> str:
    base = str(run_id or "").strip()
    return f"perf_rep_{base.removeprefix('perf_cmp_')}"


__all__ = [
    "InvalidFeedbackIdentityError",
    "build_baseline_id",
    "build_comparison_run_id",
    "build_report_id",
    "normalize_idempotency_key",
]
