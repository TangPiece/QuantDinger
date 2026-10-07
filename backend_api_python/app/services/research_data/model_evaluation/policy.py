"""ModelEvaluationPolicy 规范化与 hash。"""

from __future__ import annotations

from typing import Any

from .hashing import compute_policy_content_hash
from .policy_presets import MODEL_STANDARD_V1, get_policy_preset
from .protocol import ModelEvaluationPolicy


def resolve_policy(policy_code: str = "MODEL_STANDARD_V1") -> ModelEvaluationPolicy:
    return get_policy_preset(policy_code)


def policy_canonical_payload(policy: ModelEvaluationPolicy) -> dict[str, Any]:
    return {
        "policy_code": policy.policy_code,
        "version": policy.version,
        "metrics": list(policy.metrics),
        "ranking_ks": list(policy.ranking_ks),
        "missing_value_policy": policy.missing_value_policy,
        "min_cross_section": int(policy.min_cross_section),
        "require_pit": bool(policy.require_pit),
        "benchmark": policy.benchmark,
    }


def hash_policy(policy: ModelEvaluationPolicy) -> str:
    return compute_policy_content_hash(policy_canonical_payload(policy))


__all__ = [
    "MODEL_STANDARD_V1",
    "hash_policy",
    "policy_canonical_payload",
    "resolve_policy",
]
