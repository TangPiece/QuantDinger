"""Phase 8A：版本 content_hash（7E governance 与 8A registry 共用算法 SSOT）。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def content_hash_for_pin(
    *,
    strategy_version: str,
    model_version: str,
    dataset_hash: str,
    feature_version: str,
    extra: Mapping[str, Any] | None = None,
) -> str:
    """确定性内容 hash；7E LIVE 钉扎与 8A 版本指纹均委托此函数。"""
    payload = {
        "strategy_version": strategy_version,
        "model_version": model_version,
        "dataset_hash": dataset_hash,
        "feature_version": feature_version,
        **dict(extra or {}),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def content_hash_for_version_record(
    *,
    strategy_version: str,
    model_version: str,
    dataset_hash: str,
    feature_version: str,
    strategy_hash: str = "",
    bundle_hash: str = "",
    snapshot_id: str = "",
    model_artifact_id: str = "",
    processor_version: str = "",
    processor_hash: str = "",
    risk_policy_ref: str = "",
    execution_policy_ref: str = "",
) -> str:
    """8A 全量钉扎字段 → content_hash。"""
    return content_hash_for_pin(
        strategy_version=strategy_version,
        model_version=model_version,
        dataset_hash=dataset_hash,
        feature_version=feature_version,
        extra={
            "strategy_hash": strategy_hash,
            "bundle_hash": bundle_hash,
            "snapshot_id": snapshot_id,
            "model_artifact_id": model_artifact_id,
            "processor_version": processor_version,
            "processor_hash": processor_hash,
            "risk_policy_ref": risk_policy_ref,
            "execution_policy_ref": execution_policy_ref,
        },
    )
