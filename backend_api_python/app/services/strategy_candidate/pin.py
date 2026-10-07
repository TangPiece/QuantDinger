"""Phase 8B：Candidate lineage content_hash（证据钉扎 SSOT）。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def content_hash_for_candidate_lineage(
    *,
    candidate_version: str,
    experiment_id: str = "",
    backtest_hash: str = "",
    model_version: str = "",
    model_artifact_id: str = "",
    dataset_hash: str = "",
    snapshot_id: str = "",
    feature_version: str = "",
    processor_version: str = "",
    processor_hash: str = "",
    strategy_hash: str = "",
    strategy_definition_json: Mapping[str, Any] | None = None,
    risk_policy_ref: str = "",
    execution_policy_ref: str = "",
    evaluation_hash: str = "",
    cv_hash: str = "",
) -> str:
    """全量 research lineage → 32 字符 content_hash。"""
    payload = {
        "candidate_version": candidate_version,
        "experiment_id": experiment_id,
        "backtest_hash": backtest_hash,
        "model_version": model_version,
        "model_artifact_id": model_artifact_id,
        "dataset_hash": dataset_hash,
        "snapshot_id": snapshot_id,
        "feature_version": feature_version,
        "processor_version": processor_version,
        "processor_hash": processor_hash,
        "strategy_hash": strategy_hash,
        "strategy_definition_json": dict(strategy_definition_json or {}),
        "risk_policy_ref": risk_policy_ref,
        "execution_policy_ref": execution_policy_ref,
        "evaluation_hash": evaluation_hash,
        "cv_hash": cv_hash,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def assert_lineage_compatible(
    existing: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    lock_fields: tuple[str, ...] | None = None,
) -> None:
    """冻结后同 candidate_id 若 pin 不一致则拒。"""
    fields = lock_fields or (
        "experiment_id",
        "backtest_hash",
        "model_version",
        "model_artifact_id",
        "dataset_hash",
        "snapshot_id",
        "feature_version",
        "processor_version",
        "processor_hash",
        "strategy_hash",
        "strategy_definition_json",
        "risk_policy_ref",
        "execution_policy_ref",
        "evaluation_hash",
        "cv_hash",
        "content_hash",
    )
    for key in fields:
        if existing.get(key) != candidate.get(key):
            raise ValueError(f"{key} is immutable after lineage freeze")


__all__ = ["assert_lineage_compatible", "content_hash_for_candidate_lineage"]
