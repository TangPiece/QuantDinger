"""Model Evaluation content hash。"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from app.services.research_data.hashing import canonical_json

from .protocol import ENGINE_VERSION, EVALUATOR_VERSION


def compute_policy_content_hash(policy_payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        canonical_json(dict(policy_payload)).encode("utf-8")
    ).hexdigest()


def compute_run_content_hash(
    *,
    model_version_id: str,
    evaluation_dataset_hash: str,
    policy_content_hash: str,
    evaluation_start: str,
    evaluation_end: str,
    label_hash: str = "",
    feature_set_hash: str = "",
    snapshot_id: str = "",
) -> str:
    payload = {
        "model_version_id": model_version_id,
        "evaluation_dataset_hash": evaluation_dataset_hash,
        "policy_content_hash": policy_content_hash,
        "evaluation_start": evaluation_start,
        "evaluation_end": evaluation_end,
        "label_hash": label_hash,
        "feature_set_hash": feature_set_hash,
        "snapshot_id": snapshot_id,
        "engine_version": ENGINE_VERSION,
        "evaluator_version": EVALUATOR_VERSION,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


__all__ = ["compute_policy_content_hash", "compute_run_content_hash"]
