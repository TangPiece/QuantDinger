"""Policy / Run content hash。"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from app.services.research_data.hashing import canonical_json

from .policy import EvaluationPolicy
from .protocol import ENGINE_VERSION, FactorEvaluationRequest


def compute_policy_content_hash(policy: EvaluationPolicy) -> str:
    payload = policy.canonical_payload()
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def compute_run_content_hash(
    *,
    factor_hash: str,
    dataset_hash: str,
    factor_dataset_id: str,
    policy_content_hash: str,
    start_date: str,
    end_date: str,
    layout: str = "long",
    extra: Mapping[str, Any] | None = None,
) -> str:
    """同输入 → 同 hash；政策变更 → policy_content_hash 变 → 新 run。"""
    payload = {
        "engine_version": ENGINE_VERSION,
        "factor_hash": str(factor_hash or ""),
        "dataset_hash": str(dataset_hash or ""),
        "factor_dataset_id": str(factor_dataset_id or ""),
        "policy_content_hash": str(policy_content_hash or ""),
        "start_date": start_date,
        "end_date": end_date,
        "layout": layout,
        **dict(extra or {}),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def request_fingerprint(req: FactorEvaluationRequest, *, policy_hash: str) -> str:
    return compute_run_content_hash(
        factor_hash="",
        dataset_hash="",
        factor_dataset_id="",
        policy_content_hash=policy_hash,
        start_date=req.start_date,
        end_date=req.end_date,
        layout=req.layout,
        extra={
            "factor_ref": req.factor_ref,
            "dataset_ref": req.dataset_ref,
            "policy_id": req.policy_id,
        },
    )


__all__ = [
    "compute_policy_content_hash",
    "compute_run_content_hash",
    "request_fingerprint",
]
