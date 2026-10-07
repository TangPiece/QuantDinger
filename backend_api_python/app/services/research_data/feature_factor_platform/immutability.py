"""FeatureSet / Build 索引不可覆盖。"""

from __future__ import annotations

import json
from pathlib import Path

from .feature_set import FeatureSetDefinition
from .hashing import compute_feature_set_hash as _feature_set_hash
from .protocol import FactorBuildIndex, FeatureSetManifest


class FeatureFactorImmutabilityError(ValueError):
    """同槽位已发布且内容不一致。"""


def load_json_model(path: Path, model_cls: type):
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return model_cls.model_validate(data)


def assert_feature_set_immutable(
    existing: FeatureSetManifest,
    incoming: FeatureSetDefinition,
) -> None:
    if not existing.immutable:
        return
    new_hash = _feature_set_hash(
        code=incoming.code,
        version=incoming.version,
        member_refs=incoming.member_refs,
        processor=incoming.processor,
        schema_version=incoming.schema_version,
    )
    if existing.feature_set_hash != new_hash:
        raise FeatureFactorImmutabilityError(
            f"feature_set {incoming.code}@{incoming.version} immutable; bump version "
            f"(published={existing.feature_set_hash[:12]}… incoming={new_hash[:12]}…)"
        )


def assert_factor_build_immutable(
    existing: FactorBuildIndex,
    incoming: FactorBuildIndex,
) -> None:
    if not existing.immutable:
        return
    if existing.factor_hash != incoming.factor_hash:
        raise FeatureFactorImmutabilityError(
            f"build index for {existing.factor_ref} immutable; factor_hash mismatch"
        )
    if existing.factor_dataset_id and incoming.factor_dataset_id:
        if existing.factor_dataset_id != incoming.factor_dataset_id:
            raise FeatureFactorImmutabilityError(
                f"build index for {existing.factor_ref} immutable; dataset id mismatch"
            )


__all__ = [
    "FeatureFactorImmutabilityError",
    "assert_factor_build_immutable",
    "assert_feature_set_immutable",
    "load_json_model",
]
