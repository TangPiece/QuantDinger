"""ModelEvaluationRun 不可覆盖。"""

from __future__ import annotations

import json
from pathlib import Path

from .protocol import ModelEvaluationRun


class ModelEvaluationImmutabilityError(ValueError):
    pass


def load_json_model(path: Path, model_cls: type):
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return model_cls.model_validate(data)


def assert_run_immutable(
    existing: ModelEvaluationRun, incoming: ModelEvaluationRun
) -> None:
    if not existing.immutable:
        return
    if existing.run_content_hash != incoming.run_content_hash:
        raise ModelEvaluationImmutabilityError(
            "run_content_hash mismatch on immutable evaluation run"
        )
    if existing.status in ("SUCCEEDED", "BLOCKED", "FAILED"):
        raise ModelEvaluationImmutabilityError(
            f"cannot overwrite terminal evaluation run: {existing.status}"
        )


__all__ = [
    "ModelEvaluationImmutabilityError",
    "assert_run_immutable",
    "load_json_model",
]
