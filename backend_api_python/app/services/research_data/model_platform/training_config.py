"""TrainingConfig / ResourceConfig 规范化与 hash。"""

from __future__ import annotations

from typing import Any

from .hashing import compute_hyperparameter_hash, compute_training_config_hash
from .protocol import ResourceConfig, TrainingConfig


def normalize_training_config(raw: dict[str, Any] | TrainingConfig | None) -> dict[str, Any]:
    if isinstance(raw, TrainingConfig):
        return raw.model_dump(mode="json")
    if not raw:
        return TrainingConfig().model_dump(mode="json")
    return TrainingConfig.model_validate(raw).model_dump(mode="json")


def normalize_resource_config(raw: dict[str, Any] | ResourceConfig | None) -> dict[str, Any]:
    if isinstance(raw, ResourceConfig):
        return raw.model_dump(mode="json")
    if not raw:
        return ResourceConfig().model_dump(mode="json")
    return ResourceConfig.model_validate(raw).model_dump(mode="json")


def hash_training_config(config: dict[str, Any] | TrainingConfig | None) -> str:
    return compute_training_config_hash(normalize_training_config(config))


def compute_hp_hash(hyperparameters: dict[str, Any] | None) -> str:
    return compute_hyperparameter_hash(hyperparameters)


__all__ = [
    "compute_hp_hash",
    "hash_training_config",
    "normalize_resource_config",
    "normalize_training_config",
]
