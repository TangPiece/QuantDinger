"""Manifest / Run 不可覆盖。"""

from __future__ import annotations

import json
from pathlib import Path

from .protocol import ReproducibilityManifest, ReproducibilityRun


class ReproducibilityImmutabilityError(ValueError):
    pass


def load_json_model(path: Path, model_cls: type):
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return model_cls.model_validate(data)


def assert_manifest_immutable(
    existing: ReproducibilityManifest, incoming: ReproducibilityManifest
) -> None:
    if not existing.immutable:
        return
    if existing.repro_manifest_id != incoming.repro_manifest_id:
        raise ReproducibilityImmutabilityError("repro_manifest_id drift")
    if existing.model_dump(mode="json") != incoming.model_dump(mode="json"):
        raise ReproducibilityImmutabilityError(
            f"cannot overwrite immutable repro manifest: {existing.repro_manifest_id}"
        )


def assert_run_terminal_immutable(existing: ReproducibilityRun) -> None:
    if existing.status in ("SUCCEEDED", "FAILED") and existing.immutable:
        raise ReproducibilityImmutabilityError(
            f"cannot overwrite terminal reproducibility run: {existing.status}"
        )


__all__ = [
    "ReproducibilityImmutabilityError",
    "assert_manifest_immutable",
    "assert_run_terminal_immutable",
    "load_json_model",
]
