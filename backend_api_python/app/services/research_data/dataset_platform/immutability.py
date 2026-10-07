"""已发布 Dataset 不可覆盖同 (code, version, snapshot_id)。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.research_data.contracts import DatasetDefinition
from app.services.research_data.hashing import canonical_json

from .hashing import compute_domain_dataset_hash
from .identity import immutability_key
from .protocol import DatasetManifest


class DatasetImmutabilityError(ValueError):
    """同版本槽位已发布且 hash 不一致。"""


def assert_manifest_immutable(
    existing: DatasetManifest,
    incoming_hash: str,
) -> None:
    if not existing.immutable:
        return
    if existing.dataset_hash != incoming_hash:
        raise DatasetImmutabilityError(
            f"dataset {existing.dataset_code}@{existing.dataset_version} "
            f"snapshot={existing.snapshot_id} is immutable; bump version to publish "
            f"(published={existing.dataset_hash[:12]}… incoming={incoming_hash[:12]}…)"
        )


def assert_definition_immutable(
    existing: DatasetDefinition | dict[str, Any],
    incoming: DatasetDefinition,
) -> None:
    """Registry 中已有 definition 时，domain hash 必须一致（幂等重入）。"""
    if isinstance(existing, DatasetDefinition):
        old_def = existing
    else:
        old_def = DatasetDefinition.model_validate(existing)
    if old_def.code != incoming.code or old_def.version != incoming.version:
        return
    old_h = compute_domain_dataset_hash(old_def)
    new_h = compute_domain_dataset_hash(incoming)
    if old_h != new_h:
        raise DatasetImmutabilityError(
            f"dataset {incoming.code}@{incoming.version} snapshot={incoming.snapshot_id} "
            "definition changed; bump version"
        )
    # 关键字段字面一致性
    if canonical_json(old_def.model_dump(mode="json")) != canonical_json(
        incoming.model_dump(mode="json")
    ):
        raise DatasetImmutabilityError(
            f"dataset {incoming.code}@{incoming.version} payload changed; bump version"
        )


def load_manifest_if_present(path: Path) -> DatasetManifest | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return DatasetManifest.model_validate(data)


__all__ = [
    "DatasetImmutabilityError",
    "assert_definition_immutable",
    "assert_manifest_immutable",
    "load_manifest_if_present",
]
