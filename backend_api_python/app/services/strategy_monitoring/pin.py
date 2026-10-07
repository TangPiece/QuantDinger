"""Phase 8F：MonitorPolicy content_hash 钉扎。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .protocol import AlertRule, MarketDataPolicy


def policy_content_hash(
    *,
    policy_id: str,
    policy_version: str,
    rules: list[AlertRule] | list[Mapping[str, Any]],
    market_data: MarketDataPolicy | Mapping[str, Any] | None = None,
) -> str:
    rules_payload = [
        r.model_dump(mode="json") if hasattr(r, "model_dump") else dict(r) for r in rules
    ]
    md = (
        market_data.model_dump(mode="json")
        if hasattr(market_data, "model_dump")
        else dict(market_data or {})
    )
    payload = {
        "policy_id": str(policy_id or "").strip(),
        "policy_version": str(policy_version or "").strip(),
        "rules": rules_payload,
        "market_data": md,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


__all__ = ["policy_content_hash"]
