"""Phase 8C：ValidationPolicy content_hash（规则版本钉扎）。"""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Any

from .protocol import ValidationPolicyRules


def policy_content_hash(
    *,
    policy_id: str,
    policy_version: str,
    rules: ValidationPolicyRules | Mapping[str, Any],
) -> str:
    """policy_id + version + rules → 32 字符 hash。"""
    if isinstance(rules, ValidationPolicyRules):
        rules_payload = rules.model_dump(mode="json")
    else:
        rules_payload = dict(rules)
    payload = {
        "policy_id": str(policy_id or "").strip(),
        "policy_version": str(policy_version or "").strip(),
        "rules": rules_payload,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


__all__ = ["policy_content_hash"]
