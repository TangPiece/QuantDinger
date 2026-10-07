"""Policy + Build/Dataset → 4C/4D/4E/4F Spec。"""

from __future__ import annotations

from app.services.research_data.contracts import DatasetHandle, FactorDatasetRecord
from app.services.research_data.feature_factor_platform.protocol import FactorBuildIndex
from app.services.research_data.factor_lab.evaluation.protocol import EvaluationSpec
from app.services.research_data.factor_lab.groups.protocol import GroupSpec
from app.services.research_data.factor_lab.metrics.protocol import MetricSpec
from app.services.research_data.factor_lab.stability.protocol import StabilitySpec

from .policy import EvaluationPolicy


def build_evaluation_spec(
    policy: EvaluationPolicy,
    *,
    build_index: FactorBuildIndex,
    handle: DatasetHandle,
    factor_ds: FactorDatasetRecord,
    start_date: str,
    end_date: str,
) -> EvaluationSpec:
    """4C EvaluationSpec：universe / snapshot 来自 9A handle + factor_ds。"""
    univ_code = factor_ds.universe_code or handle.definition.universe_code
    univ_ver = handle.definition.universe_version or ""
    snap = factor_ds.snapshot_id or handle.definition.snapshot_id
    return EvaluationSpec(
        factor_dataset_id=build_index.factor_dataset_id,
        universe_code=str(univ_code or ""),
        universe_version=str(univ_ver or "") or None,
        snapshot_id=str(snap or ""),
        start_date=start_date,
        end_date=end_date,
        frequency=factor_ds.frequency or "1d",
        return_spec=policy.return_spec.model_copy(deep=True),
        price_policy=policy.price_policy.model_copy(deep=True),
        mode=policy.mode,
        exchange=policy.exchange,
        metadata={"evaluation_policy_id": policy.policy_id},
    )


def build_metric_spec(
    policy: EvaluationPolicy,
    *,
    evaluation_hash: str,
) -> MetricSpec:
    return MetricSpec(
        evaluation_hash=evaluation_hash,
        horizons=list(policy.return_spec.horizons),
        min_cross_section_size=policy.min_cross_section_size,
        direction=policy.ic_direction,
    )


def build_group_spec(
    policy: EvaluationPolicy,
    *,
    evaluation_hash: str,
) -> GroupSpec:
    return GroupSpec(
        evaluation_hash=evaluation_hash,
        group_count=policy.quantile_count,
        horizons=list(policy.return_spec.horizons),
        min_cross_section_size=policy.min_cross_section_size,
        direction=policy.ic_direction,
        cost_model=policy.cost_model.model_copy(deep=True),
    )


def build_stability_spec(
    policy: EvaluationPolicy,
    *,
    evaluation_hash: str,
) -> StabilitySpec:
    decay = policy.decay_horizons
    return StabilitySpec(
        evaluation_hash=evaluation_hash,
        rolling_windows=list(policy.rolling_windows),
        decay_horizons=list(decay) if decay is not None else None,
        regime_types=list(policy.regime_types),
        min_cross_section_size=policy.min_cross_section_size,
        direction=policy.ic_direction,
        group_count=policy.quantile_count,
        cost_model=policy.cost_model.model_copy(deep=True),
    )


__all__ = [
    "build_evaluation_spec",
    "build_group_spec",
    "build_metric_spec",
    "build_stability_spec",
]
