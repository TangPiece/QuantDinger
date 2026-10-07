"""Mining policy / run / expression hash。"""

from __future__ import annotations

import hashlib

from app.services.research_data.hashing import canonical_json

from .policy import MiningPolicy
from .protocol import ENGINE_VERSION


def compute_mining_policy_content_hash(policy: MiningPolicy) -> str:
    payload = policy.canonical_payload()
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def compute_expression_hash(canonical_dsl: str) -> str:
    text = str(canonical_dsl or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_mining_run_hash(
    *,
    dataset_hash: str,
    feature_set_hash: str,
    mining_policy_content_hash: str,
    evaluation_policy_version: str,
    random_seed: int,
) -> str:
    """复现键（锁死）。"""
    payload = {
        "engine_version": ENGINE_VERSION,
        "dataset_hash": str(dataset_hash or ""),
        "feature_set_hash": str(feature_set_hash or ""),
        "mining_policy_content_hash": str(mining_policy_content_hash or ""),
        "evaluation_policy_version": str(evaluation_policy_version or ""),
        "random_seed": int(random_seed),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


__all__ = [
    "compute_expression_hash",
    "compute_mining_policy_content_hash",
    "compute_mining_run_hash",
]
