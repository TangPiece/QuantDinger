"""Phase 8E：DriftPolicy / ExpectedBaseline content_hash 钉扎。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .protocol import DriftPolicyRule, MetricsSnapshot


def policy_content_hash(
    *,
    policy_id: str,
    policy_version: str,
    rules: list[DriftPolicyRule] | list[Mapping[str, Any]],
) -> str:
    rules_payload = [
        r.model_dump(mode="json") if hasattr(r, "model_dump") else dict(r) for r in rules
    ]
    payload = {
        "policy_id": str(policy_id or "").strip(),
        "policy_version": str(policy_version or "").strip(),
        "rules": rules_payload,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def baseline_content_hash(
    *,
    strategy_code: str,
    strategy_version: str,
    content_hash: str,
    pipeline_run_id: str,
    metrics: MetricsSnapshot,
) -> str:
    """冻结后 metrics 变更应导致 hash 不匹配 → 拒绝覆盖。"""
    payload = {
        "strategy_code": str(strategy_code or "").strip(),
        "strategy_version": str(strategy_version or "").strip(),
        "content_hash": str(content_hash or "").strip(),
        "pipeline_run_id": str(pipeline_run_id or "").strip(),
        "metrics": metrics.model_dump(mode="json"),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


__all__ = ["baseline_content_hash", "policy_content_hash"]
