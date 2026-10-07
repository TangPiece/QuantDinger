"""Phase 8C：validation_id 确定性构造（同 candidate+policy 幂等）。"""

from __future__ import annotations

import hashlib
import json
import re

_POLICY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")


class InvalidValidationIdentityError(ValueError):
    """非法 policy_id / validation_id 输入。"""


def normalize_policy_id(raw: str) -> str:
    text = str(raw or "").strip().lower()
    text = re.sub(r"[\s]+", "_", text)
    if not text or not _POLICY_ID_RE.match(text):
        raise InvalidValidationIdentityError(f"invalid policy_id: {raw!r}")
    return text


def build_validation_id(
    *,
    candidate_id: str,
    policy_id: str,
    policy_version: str,
    policy_content_hash: str,
) -> str:
    """同钉扎输入 → 同一 validation_id；Run 结果不可变。"""
    payload = {
        "candidate_id": str(candidate_id or "").strip(),
        "policy_id": normalize_policy_id(policy_id),
        "policy_version": str(policy_version or "").strip(),
        "policy_content_hash": str(policy_content_hash or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"val_{digest}"


__all__ = [
    "InvalidValidationIdentityError",
    "build_validation_id",
    "normalize_policy_id",
]
