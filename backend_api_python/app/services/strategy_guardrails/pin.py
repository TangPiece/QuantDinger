"""Phase 8G：GuardrailPolicy / AutoActionPolicy content_hash 钉扎。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .protocol import ActionMatrixEntry, AutoActionPolicyRecord, GuardrailPolicyRecord


def auto_action_policy_hash(
    *,
    policy_id: str,
    policy_version: str,
    auto_allowed: list[str],
    auto_forbidden: list[str],
    auto_resume: bool,
) -> str:
    payload = {
        "policy_id": str(policy_id or "").strip(),
        "policy_version": str(policy_version or "").strip(),
        "auto_allowed": sorted(str(x).upper() for x in auto_allowed),
        "auto_forbidden": sorted(str(x).upper() for x in auto_forbidden),
        "auto_resume": bool(auto_resume),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def guardrail_policy_hash(
    *,
    policy_id: str,
    policy_version: str,
    auto_execute: bool,
    auto_action_policy_id: str,
    auto_action_policy_version: str,
    action_matrix: list[ActionMatrixEntry] | list[Mapping[str, Any]],
) -> str:
    matrix_payload = [
        e.model_dump(mode="json") if hasattr(e, "model_dump") else dict(e)
        for e in action_matrix
    ]
    payload = {
        "policy_id": str(policy_id or "").strip(),
        "policy_version": str(policy_version or "").strip(),
        "auto_execute": bool(auto_execute),
        "auto_action_policy_id": str(auto_action_policy_id or "").strip(),
        "auto_action_policy_version": str(auto_action_policy_version or "").strip(),
        "action_matrix": matrix_payload,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def hash_guardrail_policy(record: GuardrailPolicyRecord) -> str:
    return guardrail_policy_hash(
        policy_id=record.policy_id,
        policy_version=record.policy_version,
        auto_execute=record.auto_execute,
        auto_action_policy_id=record.auto_action_policy_id,
        auto_action_policy_version=record.auto_action_policy_version,
        action_matrix=record.action_matrix,
    )


def hash_auto_action_policy(record: AutoActionPolicyRecord) -> str:
    return auto_action_policy_hash(
        policy_id=record.policy_id,
        policy_version=record.policy_version,
        auto_allowed=list(record.auto_allowed),
        auto_forbidden=list(record.auto_forbidden),
        auto_resume=record.auto_resume,
    )


__all__ = [
    "auto_action_policy_hash",
    "guardrail_policy_hash",
    "hash_auto_action_policy",
    "hash_guardrail_policy",
]
