"""Phase 8D：PromotionPolicy content_hash（规则版本钉扎）。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .protocol import PromotionPolicyRules


def policy_content_hash(
    *,
    policy_id: str,
    policy_version: str,
    transition_key: str,
    rules: PromotionPolicyRules | Mapping[str, Any],
) -> str:
    if isinstance(rules, PromotionPolicyRules):
        rules_payload = rules.model_dump(mode="json")
    else:
        rules_payload = dict(rules)
    payload = {
        "policy_id": str(policy_id or "").strip(),
        "policy_version": str(policy_version or "").strip(),
        "transition_key": str(transition_key or "").strip(),
        "rules": rules_payload,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


__all__ = ["policy_content_hash"]
