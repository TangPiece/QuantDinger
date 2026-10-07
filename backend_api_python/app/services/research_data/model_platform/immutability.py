"""TrainingRun / ModelVersion lineage 不可覆盖（9F-2 硬化）。"""

from __future__ import annotations

import json
from pathlib import Path

from .protocol import ModelVersion, TrainingRun, TrainingRunStatus


class ModelImmutabilityError(ValueError):
    pass


_VERSION_LINEAGE_FIELDS = (
    "version_content_hash",
    "dataset_hash",
    "snapshot_id",
    "feature_set_id",
    "feature_set_hash",
    "factor_portfolio_id",
    "factor_portfolio_version",
    "label_id",
    "label_hash",
    "processor_version",
    "model_config_hash",
    "hyperparameter_hash",
    "framework",
    "framework_version",
    "code_version",
    "environment_hash",
    "random_seed",
    "training_run_id",
    "artifact_id",
)


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
    """正式 version（非 DRAFT）：lineage 钉字段必须完全一致。"""
    if not existing.immutable:
        return
    formal = existing.lifecycle != "DRAFT"
    for field in _VERSION_LINEAGE_FIELDS:
        ev = getattr(existing, field, None)
        iv = getattr(incoming, field, None)
        if formal:
            if ev != iv:
                raise ModelImmutabilityError(f"immutable version field {field} drift")
        else:
            if ev not in (None, "", 0) and iv not in (None, "", 0) and ev != iv:
                raise ModelImmutabilityError(f"immutable version field {field} drift")


def assert_artifact_not_rebound(existing: ModelVersion, new_artifact_id: str) -> None:
    if existing.artifact_id and new_artifact_id and existing.artifact_id != new_artifact_id:
        raise ModelImmutabilityError(
            f"artifact_id already bound to {existing.artifact_id}; rebinding forbidden"
        )


_RUN_STATUS_ALLOWED: dict[TrainingRunStatus, set[TrainingRunStatus]] = {
    "QUEUED": {"RUNNING", "CANCELLED", "SUCCEEDED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "CANCELLED"},
    "SUCCEEDED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
}


def assert_training_run_status_transition(
    current: TrainingRunStatus, target: TrainingRunStatus
) -> None:
    if current == target:
        return
    allowed = _RUN_STATUS_ALLOWED.get(current, set())
    if target not in allowed:
        raise ModelImmutabilityError(
            f"illegal training_run status {current!r} -> {target!r}"
        )


__all__ = [
    "ModelImmutabilityError",
    "assert_artifact_not_rebound",
    "assert_training_run_immutable",
    "assert_training_run_status_transition",
    "assert_version_immutable",
    "load_json_model",
]
