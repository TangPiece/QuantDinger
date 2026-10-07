"""LibraryEntry 不可覆盖。"""

from __future__ import annotations

import json
from pathlib import Path

from .protocol import FactorLibraryEntry


class LibraryImmutabilityError(ValueError):
    pass


def load_json_model(path: Path, model_cls: type):
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return model_cls.model_validate(data)


def assert_entry_immutable(existing: FactorLibraryEntry, incoming: FactorLibraryEntry) -> None:
    if not existing.immutable:
        return
    for field in ("factor_ref", "factor_hash", "evaluation_id"):
        ev = getattr(existing, field, "")
        iv = getattr(incoming, field, "")
        if ev and iv and ev != iv:
            raise LibraryImmutabilityError(f"immutable entry field {field} drift")


__all__ = [
    "LibraryImmutabilityError",
    "assert_entry_immutable",
    "load_json_model",
]
