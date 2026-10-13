"""Register fund_cn factors into Factor Lab as PIT_SAFE FeatureDefinitions."""

from __future__ import annotations

from typing import Any

from app.services.research_data.contracts import FeatureDefinition
from app.services.research_data.factor_lab.dependencies import validate_for_backtest
from app.services.research_data.factor_lab.hash import compute_factor_hash
from app.services.research_data.factor_lab.registry_api import register_factor
from app.services.research_data.registry import ResearchRegistry

from .catalog import FACTOR_DEFINITIONS, FundFactorDef, backtest_eligible_factors, mvp_factors
from .coverage import assert_pit_safe_allowed


def to_feature(factor: FundFactorDef) -> FeatureDefinition:
    deps = [f"fundamental:{m}" for m in factor.metric_deps]
    if factor.kind == "valuation":
        deps.append("market:CNStock")
    feature = FeatureDefinition(
        code=factor.factor_id,
        version="1.0.0",
        name=factor.display_name,
        expression=factor.metric_deps[0] if factor.metric_deps else factor.factor_id,
        description=factor.formula,
        factor_type="FUNDAMENTAL",
        computation_engine="polars",
        frequency="1d",
        information_policy=factor.information_policy if factor.enabled else "UNKNOWN",
        dependencies=deps,
        schema_version="factor_daily_long@1",
        definition={
            "kind": factor.kind,
            "mvp": factor.mvp,
            "formula": factor.formula,
            "gates": {
                "RAW_OK": factor.raw_ok,
                "COMPUTE_OK": factor.compute_ok,
                "PIT_OK": factor.pit_ok,
            },
            "factor_set": "fund_cn_basic@v1",
        },
    )
    return feature.model_copy(update={"factor_hash": compute_factor_hash(feature)})


def register_mvp_factors(
    registry: ResearchRegistry,
    *,
    coverage_summary: dict[str, Any] | None = None,
    require_coverage: bool = False,
) -> list[str]:
    """Register MVP factors that pass PIT gate policy."""
    registered: list[str] = []
    for factor in mvp_factors():
        if require_coverage and coverage_summary is not None:
            assert_pit_safe_allowed(factor.factor_id, coverage_summary)
        feature = to_feature(factor)
        if feature.information_policy == "PIT_SAFE" and not validate_for_backtest(feature):
            raise ValueError(f"{factor.factor_id} failed validate_for_backtest")
        register_factor(registry, feature)
        registered.append(feature.code + "@" + feature.version)
    return registered


def register_eligible_factors(registry: ResearchRegistry) -> list[str]:
    """Register only factors with all three gates green."""
    registered: list[str] = []
    for factor in backtest_eligible_factors():
        feature = to_feature(factor)
        register_factor(registry, feature)
        registered.append(feature.code + "@" + feature.version)
    return registered


def catalog_feature_specs() -> list[dict[str, Any]]:
    return [
        {
            "factor_ref": f.factor_ref,
            "kind": f.kind,
            "mvp": f.mvp,
            "enabled": f.enabled,
            "information_policy": f.information_policy,
            "dependencies": [f"fundamental:{m}" for m in f.metric_deps],
            "gates": {
                "RAW_OK": f.raw_ok,
                "COMPUTE_OK": f.compute_ok,
                "PIT_OK": f.pit_ok,
            },
        }
        for f in FACTOR_DEFINITIONS
    ]
