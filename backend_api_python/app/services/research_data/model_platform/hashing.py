"""Model config / version / training_run 内容 hash。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _sha256_payload(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_model_config_hash(config: dict[str, Any] | None) -> str:
    return _sha256_payload({"kind": "model_config", "config": dict(config or {})})


def compute_training_config_hash(config: dict[str, Any] | None) -> str:
    return _sha256_payload({"kind": "training_config", "config": dict(config or {})})


def compute_hyperparameter_hash(hyperparameters: dict[str, Any] | None) -> str:
    return _sha256_payload(
        {"kind": "hyperparameters", "hyperparameters": dict(hyperparameters or {})}
    )


def compute_version_content_hash(
    *,
    model_code: str,
    version: str,
    dataset_hash: str,
    snapshot_id: str,
    feature_set_hash: str,
    factor_portfolio_id: str,
    factor_portfolio_version: str,
    label_hash: str,
    processor_version: str,
    model_config_hash: str,
    hyperparameter_hash: str,
    framework: str,
    framework_version: str,
    code_version: str,
    environment_hash: str,
    random_seed: int,
) -> str:
    return _sha256_payload(
        {
            "kind": "model_version",
            "model_code": model_code,
            "version": version,
            "dataset_hash": dataset_hash,
            "snapshot_id": snapshot_id,
            "feature_set_hash": feature_set_hash,
            "factor_portfolio_id": factor_portfolio_id,
            "factor_portfolio_version": factor_portfolio_version,
            "label_hash": label_hash,
            "processor_version": processor_version,
            "model_config_hash": model_config_hash,
            "hyperparameter_hash": hyperparameter_hash,
            "framework": framework,
            "framework_version": framework_version,
            "code_version": code_version,
            "environment_hash": environment_hash,
            "random_seed": int(random_seed),
        }
    )


def compute_training_run_hash(
    *,
    model_id: str,
    model_version_id: str,
    dataset_hash: str,
    feature_set_hash: str,
    factor_portfolio_hash: str,
    train_start: str,
    train_end: str,
    validation_start: str,
    validation_end: str,
    random_seed: int,
    hyperparameters: dict[str, Any],
) -> str:
    return _sha256_payload(
        {
            "kind": "training_run",
            "model_id": model_id,
            "model_version_id": model_version_id,
            "dataset_hash": dataset_hash,
            "feature_set_hash": feature_set_hash,
            "factor_portfolio_hash": factor_portfolio_hash,
            "train_start": train_start,
            "train_end": train_end,
            "validation_start": validation_start,
            "validation_end": validation_end,
            "random_seed": int(random_seed),
            "hyperparameters": dict(hyperparameters or {}),
        }
    )


__all__ = [
    "compute_hyperparameter_hash",
    "compute_model_config_hash",
    "compute_training_config_hash",
    "compute_training_run_hash",
    "compute_version_content_hash",
]
