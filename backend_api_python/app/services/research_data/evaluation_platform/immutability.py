"""EvaluationRunIndex 不可覆盖。"""

from __future__ import annotations

import json
from pathlib import Path

from .protocol import EvaluationRunIndex


class EvaluationImmutabilityError(ValueError):
    """同 content hash 槽位已发布且内容不一致。"""


def load_json_model(path: Path, model_cls: type):
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return model_cls.model_validate(data)


def assert_run_immutable(existing: EvaluationRunIndex, incoming: EvaluationRunIndex) -> None:
    if not existing.immutable:
        return
    if existing.run_content_hash != incoming.run_content_hash:
        raise EvaluationImmutabilityError("run_content_hash mismatch on immutable slot")
    for field in (
        "factor_hash",
        "dataset_hash",
        "policy_content_hash",
        "evaluation_hash",
        "metric_hash",
        "group_evaluation_hash",
        "stability_hash",
    ):
        ev = getattr(existing, field, "")
        iv = getattr(incoming, field, "")
        if ev and iv and ev != iv:
            raise EvaluationImmutabilityError(
                f"immutable run field {field} drift: {ev[:12]}… vs {iv[:12]}…"
            )


__all__ = [
    "EvaluationImmutabilityError",
    "assert_run_immutable",
    "load_json_model",
]
