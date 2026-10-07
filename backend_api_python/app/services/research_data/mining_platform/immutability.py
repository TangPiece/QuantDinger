"""MiningRunIndex 不可覆盖。"""

from __future__ import annotations

import json
from pathlib import Path

from .protocol import MiningRunIndex


class MiningImmutabilityError(ValueError):
    pass


def load_json_model(path: Path, model_cls: type):
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return model_cls.model_validate(data)


def assert_run_immutable(existing: MiningRunIndex, incoming: MiningRunIndex) -> None:
    if not existing.immutable:
        return
    if existing.mining_run_hash != incoming.mining_run_hash:
        raise MiningImmutabilityError("mining_run_hash mismatch on immutable slot")
    for field in ("dataset_hash", "feature_set_hash", "mining_policy_content_hash"):
        ev = getattr(existing, field, "")
        iv = getattr(incoming, field, "")
        if ev and iv and ev != iv:
            raise MiningImmutabilityError(f"immutable run field {field} drift")


__all__ = [
    "MiningImmutabilityError",
    "assert_run_immutable",
    "load_json_model",
]
