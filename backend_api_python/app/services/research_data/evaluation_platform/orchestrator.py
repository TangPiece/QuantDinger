"""编排 4C → 4D → 4E → 4F（不重写数学）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import DatasetHandle, FactorDatasetRecord
from app.services.research_data.feature_factor_platform.protocol import FactorBuildIndex
from app.services.research_data.factor_lab import (
    FactorEvaluationService,
    FactorGroupEvaluationService,
    FactorMetricsService,
    FactorStabilityService,
)
from app.services.research_data.registry import ResearchRegistry

from .adapters import (
    build_evaluation_spec,
    build_group_spec,
    build_metric_spec,
    build_stability_spec,
)
from .policy import EvaluationPolicy


class EvaluationOrchestratorError(RuntimeError):
    pass


@dataclass
class PipelineArtifacts:
    evaluation_hash: str
    metric_hash: str
    group_evaluation_hash: str
    stability_hash: str
    resolved_direction: Literal["POSITIVE", "NEGATIVE"]
    raw_metrics: dict[str, Any]


class EvaluationOrchestrator:
    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        evaluation_svc: FactorEvaluationService | None = None,
        metrics_svc: FactorMetricsService | None = None,
        groups_svc: FactorGroupEvaluationService | None = None,
        stability_svc: FactorStabilityService | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._eval = evaluation_svc or FactorEvaluationService(
            None, registry, store  # type: ignore[arg-type]
        )
        self._metrics = metrics_svc or FactorMetricsService(store, registry)
        self._groups = groups_svc or FactorGroupEvaluationService(store, registry)
        self._stability = stability_svc or FactorStabilityService(store, registry)

    def run(
        self,
        policy: EvaluationPolicy,
        *,
        build_index: FactorBuildIndex,
        handle: DatasetHandle,
        factor_ds: FactorDatasetRecord,
        start_date: str,
        end_date: str,
        lab_metadata: dict[str, Any] | None = None,
    ) -> PipelineArtifacts:
        meta = dict(lab_metadata or {})
        spec = build_evaluation_spec(
            policy,
            build_index=build_index,
            handle=handle,
            factor_ds=factor_ds,
            start_date=start_date,
            end_date=end_date,
        )
        try:
            ev = self._eval.run(spec, metadata=meta)
        except Exception as exc:
            raise EvaluationOrchestratorError(f"4C evaluation failed: {exc}") from exc

        eval_hash = ev.record.evaluation_hash
        mspec = build_metric_spec(policy, evaluation_hash=eval_hash)
        try:
            metrics = self._metrics.run(eval_hash, mspec, metadata=meta)
        except Exception as exc:
            raise EvaluationOrchestratorError(f"4D metrics failed: {exc}") from exc

        direction = self._resolve_direction(policy, metrics, meta)
        meta = {**meta, "resolved_direction": direction}

        gspec = build_group_spec(policy, evaluation_hash=eval_hash)
        try:
            groups = self._groups.run(eval_hash, gspec, metadata=meta)
        except Exception as exc:
            raise EvaluationOrchestratorError(f"4E groups failed: {exc}") from exc

        sspec = build_stability_spec(policy, evaluation_hash=eval_hash)
        try:
            stability = self._stability.run(eval_hash, sspec, metadata=meta)
        except Exception as exc:
            raise EvaluationOrchestratorError(f"4F stability failed: {exc}") from exc

        raw = self._collect_raw_metrics(metrics, groups, stability)
        return PipelineArtifacts(
            evaluation_hash=eval_hash,
            metric_hash=metrics.metric_hash,
            group_evaluation_hash=groups.group_evaluation_hash,
            stability_hash=stability.stability_hash,
            resolved_direction=direction,
            raw_metrics=raw,
        )

    def _resolve_direction(
        self,
        policy: EvaluationPolicy,
        metrics: Any,
        meta: dict[str, Any],
    ) -> Literal["POSITIVE", "NEGATIVE"]:
        if policy.ic_direction in ("POSITIVE", "NEGATIVE"):
            return policy.ic_direction  # type: ignore[return-value]
        cand = meta.get("resolved_direction")
        if cand in ("POSITIVE", "NEGATIVE"):
            return cand  # type: ignore[return-value]
        primary_h = policy.return_spec.horizons[0]
        summary = next(
            (s for s in metrics.summaries if int(s.horizon) == int(primary_h)),
            metrics.summaries[0] if metrics.summaries else None,
        )
        if summary is not None and summary.mean_ic is not None:
            return "POSITIVE" if float(summary.mean_ic) >= 0 else "NEGATIVE"
        return "POSITIVE"

    def _collect_raw_metrics(
        self, metrics: Any, groups: Any, stability: Any
    ) -> dict[str, Any]:
        raw: dict[str, Any] = {"ic_by_horizon": {}, "group_by_horizon": {}, "stability_by_horizon": {}}
        for s in metrics.summaries:
            raw["ic_by_horizon"][str(s.horizon)] = {
                "mean_ic": s.mean_ic,
                "mean_rank_ic": s.mean_rank_ic,
                "ic_ir": s.ic_ir,
                "std_ic": s.std_ic,
            }
        for s in groups.summaries:
            raw["group_by_horizon"][str(s.horizon)] = {
                "long_short_return": s.mean_long_short_return,
                "turnover": s.mean_turnover,
                "estimated_cost": s.mean_estimated_cost,
            }
        for s in stability.summaries:
            icm = s.ic_stability_metrics_json or {}
            raw["stability_by_horizon"][str(s.horizon)] = {
                "ic_stability": icm.get("ic_stability") or icm.get("mean_ic_stability"),
                "rank_ic_stability": icm.get("rank_ic_stability"),
                "decay_summary": s.decay_summary_json,
            }
        return raw


__all__ = ["EvaluationOrchestrator", "EvaluationOrchestratorError", "PipelineArtifacts"]
