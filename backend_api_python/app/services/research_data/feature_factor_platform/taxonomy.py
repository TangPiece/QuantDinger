"""Feature / Factor / Alpha 分层校验（Signal 不在本阶段）。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from app.services.research_data.contracts import FeatureDefinition

ASSET_KIND_KEY = "asset_kind"


class AssetKind(str, Enum):
    FEATURE = "FEATURE"
    FACTOR = "FACTOR"
    ALPHA = "ALPHA"


class TaxonomyError(ValueError):
    """资产层与 API 不匹配。"""


def read_asset_kind(feature: FeatureDefinition) -> AssetKind:
    """读取 asset_kind；旧 4A 行缺省为 FACTOR。"""
    raw = (feature.definition or {}).get(ASSET_KIND_KEY)
    if raw is None or str(raw).strip() == "":
        return AssetKind.FACTOR
    text = str(raw).strip().upper()
    if text == "SIGNAL":
        raise TaxonomyError("Signal 不在 Phase 9B 范围")
    try:
        return AssetKind(text)
    except ValueError as exc:
        raise TaxonomyError(f"unknown asset_kind={raw!r}") from exc


def with_asset_kind(
    feature: FeatureDefinition,
    kind: AssetKind,
    *,
    extra_definition: dict[str, Any] | None = None,
) -> FeatureDefinition:
    """写入 definition.asset_kind（不破坏其它 sidecar）。"""
    sidecar = dict(feature.definition or {})
    sidecar[ASSET_KIND_KEY] = kind.value
    if extra_definition:
        sidecar.update(extra_definition)
    return feature.model_copy(update={"definition": sidecar})


def assert_kind(feature: FeatureDefinition, expected: AssetKind) -> None:
    actual = read_asset_kind(feature)
    if actual != expected:
        raise TaxonomyError(
            f"expected asset_kind={expected.value}, got {actual.value} for "
            f"{feature.code}@{feature.version}"
        )


def assert_buildable_factor(feature: FeatureDefinition) -> None:
    kind = read_asset_kind(feature)
    if kind == AssetKind.ALPHA:
        raise TaxonomyError("Alpha 仅注册，不可 build_factor")
    if kind == AssetKind.FEATURE:
        raise TaxonomyError("Feature 请走 build_feature_set，不可 build_factor")


__all__ = [
    "ASSET_KIND_KEY",
    "AssetKind",
    "TaxonomyError",
    "assert_buildable_factor",
    "assert_kind",
    "read_asset_kind",
    "with_asset_kind",
]
