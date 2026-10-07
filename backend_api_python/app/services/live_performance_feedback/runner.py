"""Phase 8E：LivePerformanceFeedbackService 门面（只观察，无自动降级 / OMS）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.services.research_data.registry import ResearchRegistry

from .attribution import build_return_attribution
from .baseline import BaselineImmutableError, assert_baseline_immutable, build_frozen_baseline
from .bridge_from_promotion import BridgeFromPromotionError, load_promotion_baseline_context
from .collectors import collect_from_controlled_live, collect_from_inject, collect_from_shadow
from .compare import compare_metrics
from .fsm import assert_transition, pipeline_statuses
from .identity import build_baseline_id, build_comparison_run_id, normalize_idempotency_key
from .policy import resolve_drift_policy
from .protocol import (
    ActualSource,
    ExpectedBaseline,
    MetricsSnapshot,
    PerformanceComparisonRun,
    ProductionDriftReport,
)
from .report import build_drift_report
from .writers import PerformanceFeedbackWriter


class PerformanceFeedbackError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LivePerformanceFeedbackService:
    """Research Expected → Production Actual → Drift Report。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        promotion: Any | None = None,
        writer: PerformanceFeedbackWriter | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._promotion = promotion
        self._writer = writer or PerformanceFeedbackWriter(registry)
        self._baselines: dict[str, ExpectedBaseline] = {}
        self._runs: dict[str, PerformanceComparisonRun] = {}
        self._reports: dict[str, ProductionDriftReport] = {}

    def _load_baseline(self, baseline_id: str) -> ExpectedBaseline:
        bid = str(baseline_id).strip()
        if bid in self._baselines:
            return self._baselines[bid]
        row = self._registry.get_performance_expected_baseline(bid)
        from .protocol import MetricsSnapshot as MS

        base = ExpectedBaseline(
            baseline_id=row.baseline_id,
            strategy_code=row.strategy_code,
            strategy_version=row.strategy_version,
            content_hash=row.content_hash,
            candidate_id=row.candidate_id,
            validation_id=row.validation_id,
            pipeline_run_id=row.pipeline_run_id,
            dataset_hash=row.dataset_hash,
            snapshot_id=row.snapshot_id,
            model_version=row.model_version,
            feature_version=row.feature_version,
            backtest_hash=row.backtest_hash,
            baseline_type=row.baseline_type,  # type: ignore[arg-type]
            metrics_snapshot=MS.model_validate(row.metrics_snapshot_json or {}),
            drift_policy_id=row.drift_policy_id,
            drift_policy_version=row.drift_policy_version,
            drift_policy_content_hash=row.drift_policy_content_hash,
            immutable=bool(row.immutable),
            created_at=row.created_at or "",
            storage_uri=row.storage_uri or "",
        )
        self._baselines[bid] = base
        return base

    def _load_baseline_by_promotion(self, pipeline_run_id: str) -> ExpectedBaseline | None:
        pid = str(pipeline_run_id or "").strip()
        try:
            row = self._registry.get_performance_expected_baseline_by_promotion(pid)
        except Exception:
            return None
        return self._load_baseline(row.baseline_id)

    def _load_run(self, run_id: str) -> PerformanceComparisonRun:
        rid = str(run_id).strip()
        if rid in self._runs:
            return self._runs[rid]
        row = self._registry.get_performance_comparison_run(rid)
        from .protocol import DriftFinding, MetricDeviation, MetricsSnapshot as MS

        run = PerformanceComparisonRun(
            run_id=row.run_id,
            strategy_code=row.strategy_code,
            baseline_id=row.baseline_id,
            actual_source=row.actual_source,  # type: ignore[arg-type]
            window_start=row.window_start or "",
            window_end=row.window_end or "",
            idempotency_key=row.idempotency_key or "",
            status=row.status,  # type: ignore[arg-type]
            policy_id=row.policy_id,
            policy_version=row.policy_version,
            policy_content_hash=row.policy_content_hash,
            actual_metrics=MS.model_validate(row.actual_metrics_json or {}),
            deviations=[MetricDeviation.model_validate(d) for d in (row.deviation_json or [])],
            findings=[DriftFinding.model_validate(f) for f in (row.drift_findings_json or [])],
            report_id=row.report_id or "",
            started_at=row.started_at or "",
            completed_at=row.completed_at or "",
            storage_uri=row.storage_uri or "",
        )
        self._runs[rid] = run
        return run

    def freeze_baseline_from_promotion(
        self,
        pipeline_run_id: str,
        *,
        metrics_inject: Mapping[str, Any] | None = None,
    ) -> ExpectedBaseline:
        """8D COMPLETED 后冻结 ExpectedBaseline（幂等；禁止改 metrics）。"""
        pid = str(pipeline_run_id or "").strip()
        existing = self._load_baseline_by_promotion(pid)
        if existing is not None:
            if metrics_inject:
                inj = collect_from_inject(metrics_inject)
                try:
                    assert_baseline_immutable(existing, metrics=inj)
                except BaselineImmutableError as exc:
                    raise PerformanceFeedbackError(str(exc)) from exc
            return existing

        policy = resolve_drift_policy(self._registry)
        self._writer.write_policy(policy)

        try:
            ctx, metrics = load_promotion_baseline_context(
                self._registry,
                pipeline_run_id=pid,
                promotion_service=self._promotion,
                metrics_inject=metrics_inject,
            )
        except BridgeFromPromotionError as exc:
            raise PerformanceFeedbackError(str(exc)) from exc

        baseline_id = build_baseline_id(pipeline_run_id=pid)
        frozen = build_frozen_baseline(
            baseline_id=baseline_id,
            strategy_code=ctx.strategy_code,
            strategy_version=ctx.strategy_version,
            content_hash=ctx.content_hash,
            candidate_id=ctx.candidate_id,
            validation_id=ctx.validation_id,
            pipeline_run_id=ctx.pipeline_run_id,
            metrics=metrics,
            drift_policy_id=policy.policy_id,
            drift_policy_version=policy.policy_version,
            drift_policy_content_hash=policy.policy_content_hash,
            dataset_hash=ctx.dataset_hash,
            snapshot_id=ctx.snapshot_id,
            model_version=ctx.model_version,
            feature_version=ctx.feature_version,
            backtest_hash=ctx.backtest_hash,
        )
        saved = self._writer.write_baseline(frozen)
        self._baselines[saved.baseline_id] = saved
        return saved

    def run_comparison(
        self,
        *,
        baseline_id: str,
        actual_source: ActualSource,
        window_start: str,
        window_end: str,
        idempotency_key: str,
        inject: Mapping[str, Any] | None = None,
    ) -> PerformanceComparisonRun:
        """对比 baseline vs actual；同 window 幂等。"""
        baseline = self._load_baseline(baseline_id)
        ikey = normalize_idempotency_key(idempotency_key)
        run_id = build_comparison_run_id(
            baseline_id=baseline_id,
            actual_source=actual_source,
            window_start=window_start,
            window_end=window_end,
            idempotency_key=ikey,
        )
        try:
            existing = self._load_run(run_id)
            if existing.status == "PUBLISHED":
                return existing
        except Exception:
            existing = None

        policy = resolve_drift_policy(
            self._registry,
            policy_id=baseline.drift_policy_id or None,
            policy_version=baseline.drift_policy_version or None,
        )

        started = _now()
        run = PerformanceComparisonRun(
            run_id=run_id,
            strategy_code=baseline.strategy_code,
            baseline_id=baseline_id,
            actual_source=actual_source,
            window_start=window_start,
            window_end=window_end,
            idempotency_key=ikey,
            status="CREATED",
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            policy_content_hash=policy.policy_content_hash,
            started_at=started,
        )
        self._writer.write_run(run)

        inj = dict(inject or {})
        try:
            for status in pipeline_statuses()[1:]:
                assert_transition(run.status, status)
                if status == "COLLECTING":
                    if actual_source == "SHADOW":
                        actual = collect_from_shadow(
                            self._registry,
                            strategy_code=baseline.strategy_code,
                            inject=inj,
                        )
                    elif actual_source == "CONTROLLED_LIVE":
                        actual = collect_from_controlled_live(
                            self._registry,
                            strategy_code=baseline.strategy_code,
                            inject=inj,
                        )
                    else:
                        actual = collect_from_inject(inj)
                    run = run.model_copy(update={"status": status, "actual_metrics": actual})
                elif status == "COMPUTING":
                    deviations = compare_metrics(baseline.metrics_snapshot, run.actual_metrics)
                    for d in deviations:
                        pass
                    run = run.model_copy(update={"status": status, "deviations": deviations})
                elif status == "ATTRIBUTING":
                    run = run.model_copy(update={"status": status})
                elif status == "EVALUATED":
                    report = build_drift_report(
                        run,
                        policy=policy,
                        baseline_metrics=baseline.metrics_snapshot,
                        attribution=build_return_attribution(
                            baseline.metrics_snapshot,
                            run.actual_metrics,
                            run.deviations,
                        ),
                    )
                    run = run.model_copy(
                        update={
                            "status": status,
                            "findings": report.findings,
                            "report_id": report.report_id,
                        }
                    )
                    self._reports[report.report_id] = report
                    self._writer.write_report_artifact(report)
                elif status == "PUBLISHED":
                    run = run.model_copy(
                        update={"status": status, "completed_at": _now()}
                    )
                self._writer.write_run(run)

            self._runs[run.run_id] = run
            return run
        except Exception as exc:
            failed = run.model_copy(update={"status": "FAILED", "completed_at": _now()})
            self._writer.write_run(failed)
            raise PerformanceFeedbackError(str(exc)) from exc

    def get_baseline(self, baseline_id: str) -> ExpectedBaseline:
        return self._load_baseline(baseline_id)

    def get_run(self, run_id: str) -> PerformanceComparisonRun:
        return self._load_run(run_id)

    def list_runs(self, strategy_code: str) -> list[PerformanceComparisonRun]:
        rows = self._registry.list_performance_comparison_runs(strategy_code=strategy_code)
        out = [self._load_run(r.run_id) for r in rows]
        out.sort(key=lambda r: r.completed_at or r.started_at or "")
        return out

    def get_report(self, run_id: str) -> ProductionDriftReport:
        run = self._load_run(run_id)
        if run.report_id and run.report_id in self._reports:
            return self._reports[run.report_id]
        baseline = self._load_baseline(run.baseline_id)
        policy = resolve_drift_policy(
            self._registry,
            policy_id=run.policy_id or baseline.drift_policy_id,
            policy_version=run.policy_version or baseline.drift_policy_version,
        )
        report = build_drift_report(
            run,
            policy=policy,
            baseline_metrics=baseline.metrics_snapshot,
            attribution=build_return_attribution(
                baseline.metrics_snapshot,
                run.actual_metrics,
                run.deviations,
            ),
        )
        self._reports[report.report_id] = report
        return report

    def latest_drift_scalars(self, strategy_code: str) -> dict[str, float]:
        """供 8D precondition inject 只读适配（shadow_drift 等）。"""
        runs = self.list_runs(strategy_code)
        if not runs:
            return {}
        latest = runs[-1]
        m = latest.actual_metrics
        out = {
            "shadow_drift": float(m.shadow_drift),
            "max_drawdown": float(m.max_drawdown),
            "slippage": float(m.slippage_bps) / 10000.0,
            "reject_rate": float(m.reject_rate),
            "signal_correlation": float(m.signal_correlation),
        }
        for f in latest.findings:
            if f.severity == "CRITICAL":
                out["drift_critical"] = 1.0
                break
        return out


__all__ = ["LivePerformanceFeedbackService", "PerformanceFeedbackError"]
