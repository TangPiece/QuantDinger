"""TrainingRun / ModelVersion lineage 不可覆盖。"""

from __future__ import annotations

import json
from pathlib import Path

from .protocol import ModelVersion, TrainingRun


class ModelImmutabilityError(ValueError):
    pass


def load_json_model(path: Path, model_cls: type):
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return model_cls.model_validate(data)


def assert_training_run_immutable(existing: TrainingRun, incoming: TrainingRun) -> None:
    if not existing.immutable:
        return
    if existing.training_run_hash != incoming.training_run_hash:
        raise ModelImmutabilityError("training_run_hash mismatch on immutable slot")
    for field in (
        "dataset_hash",
        "feature_set_hash",
        "factor_portfolio_hash",
        "random_seed",
        "train_start",
        "train_end",
    ):
        ev = getattr(existing, field, None)
        iv = getattr(incoming, field, None)
        if ev not in (None, "") and iv not in (None, "") and ev != iv:
            raise ModelImmutabilityError(f"immutable training_run field {field} drift")
    if existing.hyperparameters and incoming.hyperparameters:
        if existing.hyperparameters != incoming.hyperparameters:
            raise ModelImmutabilityError("immutable hyperparameters drift")


def assert_version_immutable(existing: ModelVersion, incoming: ModelVersion) -> None:
    if not existing.immutable:
        return
    for field in (
        "version_content_hash",
        "dataset_hash",
        "feature_set_hash",
        "model_config_hash",
        "hyperparameter_hash",
        "label_hash",
        "random_seed",
    ):
        ev = getattr(existing, field, None)
        iv = getattr(incoming, field, None)
        if ev not in (None, "", 0) and iv not in (None, "", 0) and ev != iv:
            raise ModelImmutabilityError(f"immutable version field {field} drift")


__all__ = [
    "ModelImmutabilityError",
    "assert_training_run_immutable",
    "assert_version_immutable",
    "load_json_model",
]
