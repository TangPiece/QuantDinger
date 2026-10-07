"""Phase 9C Evaluation Platform golden 环境。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.research_data.evaluation_platform.policy import EvaluationPolicy
from app.services.research_data.evaluation_platform.policy_presets import register_policy
from app.services.research_data.evaluation_platform.runner import FactorEvaluationPlatformService
from app.services.research_data.factor_lab.evaluation.artifact_store import (
    EvaluationArtifactStore as LabEvalArtifactStore,
)
from app.services.research_data.factor_lab.metrics.artifact_store import MetricArtifactStore
from app.services.research_data.factor_lab.groups.artifact_store import GroupArtifactStore
from app.services.research_data.factor_lab.stability.artifact_store import StabilityArtifactStore
from app.services.research_data.factor_lab import (
    FactorEvaluationService,
    FactorGroupEvaluationService,
    FactorMetricsService,
    FactorStabilityService,
)
from feature_factor_platform_golden.golden import (
    GOLDEN_DATASET_REF,
    GOLDEN_FACTOR_REF,
    compute_metadata_inject,
    golden_factor_definition,
    make_feature_factor_env,
)
from factor_lab_compute.golden import INSTRUMENTS

GOLDEN_POLICY_ID = "default_equity_factor_v1"
GOLDEN_POLICY_ALT_ID = "phase9c_golden_alt_v1"


def register_golden_policies() -> None:
    """小截面 golden 用 policy（quantile=2, min_cs=3）。"""
    base = EvaluationPolicy(
        policy_id=GOLDEN_POLICY_ID,
        version="1.0.0",
        name="Golden equity eval",
        min_cross_section_size=3,
        quantile_count=2,
    )
    register_policy(base)
    alt = base.model_copy(
        update={
            "policy_id": GOLDEN_POLICY_ALT_ID,
            "return_spec": base.return_spec.model_copy(
                update={"horizons": [1, 5, 10]}
            ),
        }
    )
    register_policy(alt)


def _synthetic_factor_records(days: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, day in enumerate(days):
        for j, ik in enumerate(INSTRUMENTS):
            rows.append(
                {
                    "instrument_key": ik,
                    "factor_date": day,
                    "factor_value": 0.05 + i * 0.01 + j * 0.001,
                }
            )
    return rows


def evaluation_inject(*, gate_blocked: bool = False, days: list[Any] | None = None) -> dict[str, Any]:
    """4C–4F 测试注入：universe + 小截面 policy + factor 行。"""
    section: dict[str, Any] = {
        "policy_overrides": {
            "min_cross_section_size": 3,
            "quantile_count": 2,
        },
        "lab_metadata": {
            "instruments": INSTRUMENTS,
            "universe_members": set(INSTRUMENTS),
            "force_recompute": True,
        },
    }
    if days:
        section["lab_metadata"]["factor_records"] = _synthetic_factor_records(days)
    if gate_blocked:
        section["gate_override"] = {"verdict": "BLOCKED", "reasons": ["golden_blocked"]}
    return {"evaluation_platform": section}


def make_evaluation_platform_env(
    tmp: Path,
    *,
    build_factor: bool = True,
) -> tuple[FactorEvaluationPlatformService, Any, Any, list[Any], tuple[str, str]]:
    """9A + 9B + 9C 单 registry / canonical 根。"""
    register_golden_policies()
    ff, ds_svc, registry, query, _compute, days = make_feature_factor_env(tmp / "stack")
    store = query._store  # type: ignore[attr-defined]
    base_art = tmp / "stack" / "eval_platform_art"
    ff.register_factor(golden_factor_definition())
    eval_short = (days[0].isoformat(), days[min(12, len(days) - 1)].isoformat())
    if build_factor:
        ff.build_factor(
            GOLDEN_FACTOR_REF,
            GOLDEN_DATASET_REF,
            window=eval_short,
            inject=compute_metadata_inject(),
        )
    lab_eval_art = LabEvalArtifactStore(root=base_art / "lab_eval")
    svc = FactorEvaluationPlatformService(
        base_art / "platform",
        registry,
        factor_svc=ff,
        dataset_svc=ds_svc,
        query=query,
        canonical_store=store,
        evaluation_svc=FactorEvaluationService(
            query, registry, store, artifact_store=lab_eval_art
        ),
        metrics_svc=FactorMetricsService(
            store, registry, artifact_store=MetricArtifactStore(root=base_art / "metrics")
        ),
        groups_svc=FactorGroupEvaluationService(
            store, registry, artifact_store=GroupArtifactStore(root=base_art / "groups")
        ),
        stability_svc=FactorStabilityService(
            store, registry, artifact_store=StabilityArtifactStore(root=base_art / "stability")
        ),
    )
    return svc, ds_svc, registry, days, eval_short


__all__ = [
    "GOLDEN_DATASET_REF",
    "GOLDEN_FACTOR_REF",
    "GOLDEN_POLICY_ALT_ID",
    "GOLDEN_POLICY_ID",
    "evaluation_inject",
    "make_evaluation_platform_env",
    "register_golden_policies",
]
