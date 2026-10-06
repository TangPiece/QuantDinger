"""Factor Lab 对 Registry 的薄封装：注册 / 读取 / Dataset 登记。"""

from __future__ import annotations

from app.services.research_data.contracts import (
    FactorDatasetRecord,
    FeatureDefinition,
)
from app.services.research_data.registry import ResearchRegistry

from .dependencies import validate_dependencies, validate_for_backtest
from .hash import compute_factor_hash
from .immutability import ensure_factor_hash
from .models import FactorSpec


def register_factor(
    registry: ResearchRegistry,
    feature: FeatureDefinition | FactorSpec,
    *,
    validate_deps: bool = True,
) -> FeatureDefinition:
    """校验依赖、填充 factor_hash、写入 Registry（不可变）。"""
    feat = (
        feature.to_feature()
        if isinstance(feature, FactorSpec)
        else FeatureDefinition.model_validate(feature.model_dump(mode="json"))
    )
    if validate_deps:
        validate_dependencies(feat, registry)
    feat = ensure_factor_hash(feat)
    # 再算一次保证一致
    feat = feat.model_copy(update={"factor_hash": compute_factor_hash(feat)})
    registry.upsert_feature(feat)
    return feat


def get_factor(registry: ResearchRegistry, factor_ref: str) -> FactorSpec:
    """读取 Feature 并转为 FactorSpec。"""
    return FactorSpec.from_feature(registry.get_feature(factor_ref))


def register_factor_dataset(
    registry: ResearchRegistry,
    record: FactorDatasetRecord,
) -> FactorDatasetRecord:
    """登记 FactorDataset 索引。"""
    registry.upsert_factor_dataset(record)
    return record


def get_factor_dataset(
    registry: ResearchRegistry, factor_dataset_id: str
) -> FactorDatasetRecord:
    """读取 FactorDataset。"""
    return registry.get_factor_dataset(factor_dataset_id)


def is_backtest_eligible(registry: ResearchRegistry, factor_ref: str) -> bool:
    """是否允许进入正式回测（PIT 门禁）。"""
    feat = registry.get_feature(factor_ref)
    return validate_for_backtest(feat)
