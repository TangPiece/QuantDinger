"""Phase 8D：request_id / pipeline_run_id 确定性构造。"""

from __future__ import annotations

import hashlib
import json
import re
from uuid import uuid4

_KEY_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")


class InvalidPromotionIdentityError(ValueError):
    """非法 idempotency / request 输入。"""


def normalize_idempotency_key(raw: str) -> str:
    text = str(raw or "").strip()
    if not text or not _KEY_RE.match(text):
        raise InvalidPromotionIdentityError(f"invalid idempotency_key: {raw!r}")
    return text


def build_pipeline_run_id(
    *,
    strategy_code: str,
    idempotency_key: str,
    validation_id: str,
    to_environment: str,
) -> str:
    """同钉扎输入 → 同一 pipeline_run_id（execute 幂等）。"""
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "idempotency_key": normalize_idempotency_key(idempotency_key),
        "validation_id": str(validation_id or "").strip(),
        "to_environment": str(to_environment or "").strip().upper(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"promo_run_{digest}"


def build_request_id(*, pipeline_run_id: str) -> str:
    """一 Run 一 Request；与 pipeline_run_id 1:1。"""
    base = str(pipeline_run_id or "").strip()
    if not base:
        raise InvalidPromotionIdentityError("pipeline_run_id required")
    return f"promo_req_{base.removeprefix('promo_run_')}"


def new_rollback_id() -> str:
    return "promo_rb_" + uuid4().hex[:16]


__all__ = [
    "InvalidPromotionIdentityError",
    "build_pipeline_run_id",
    "build_request_id",
    "new_rollback_id",
    "normalize_idempotency_key",
]
