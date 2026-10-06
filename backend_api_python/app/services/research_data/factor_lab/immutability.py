"""Factor / Feature 版本不可变。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.contracts import FeatureDefinition
from app.services.research_data.hashing import canonical_json

from .hash import compute_factor_hash


class FeatureImmutabilityError(ValueError):
    """同一 code@version 禁止修改定义；须 bump version。"""


def ensure_factor_hash(feature: FeatureDefinition) -> FeatureDefinition:
    """若缺失则填充 factor_hash。"""
    h = compute_factor_hash(feature)
    if feature.factor_hash and feature.factor_hash != h:
        # 调用方传入了与内容不一致的 hash → 以计算值为准
        return feature.model_copy(update={"factor_hash": h})
    if not feature.factor_hash:
        return feature.model_copy(update={"factor_hash": h})
    return feature


def assert_feature_immutable(
    existing: FeatureDefinition | dict[str, Any],
    incoming: FeatureDefinition,
) -> None:
    """已存在同 code@version 时，factor_hash 必须一致（同内容幂等）。"""
    if isinstance(existing, FeatureDefinition):
        old = existing
    else:
        old = FeatureDefinition.model_validate(existing)
    old_h = old.factor_hash or compute_factor_hash(old)
    new_h = incoming.factor_hash or compute_factor_hash(incoming)
    if old_h != new_h:
        raise FeatureImmutabilityError(
            f"feature {incoming.code}@{incoming.version} is immutable; "
            f"bump version to change definition (old_hash={old_h[:12]}… "
            f"new_hash={new_h[:12]}…)"
        )
    # 额外：关键字段字面一致性（防 hash 算法漂移时漏检）
    for key in (
        "expression",
        "schema_version",
        "computation_engine",
        "engine_version",
        "factor_type",
        "information_policy",
        "frequency",
        "processor_ref",
    ):
        if getattr(old, key) != getattr(incoming, key):
            raise FeatureImmutabilityError(
                f"feature {incoming.code}@{incoming.version} field {key} changed; "
                "bump version"
            )
    if canonical_json(sorted(old.dependencies or [])) != canonical_json(
        sorted(incoming.dependencies or [])
    ):
        raise FeatureImmutabilityError(
            f"feature {incoming.code}@{incoming.version} dependencies changed; "
            "bump version"
        )
