"""Phase 8E：Baseline / ComparisonRun / DriftPolicy → D1 + R2。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .artifact_store import PerformanceFeedbackArtifactStore
from .protocol import (
    ENGINE_VERSION,
    DriftPolicyRecord,
    ExpectedBaseline,
    PerformanceComparisonRun,
    ProductionDriftReport,
)


class PerformanceFeedbackWriter:
    """索引与 artifact 写入。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: PerformanceFeedbackArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or PerformanceFeedbackArtifactStore()

    def write_policy(self, policy: DriftPolicyRecord) -> None:
        from app.services.research_data.contracts import DriftPolicySummary

        self._registry.upsert_drift_policy(
            DriftPolicySummary(
                policy_id=policy.policy_id,
                policy_version=policy.policy_version,
                policy_content_hash=policy.policy_content_hash,
                rules_json=[r.model_dump(mode="json") for r in policy.rules],
                engine_version=policy.engine_version or ENGINE_VERSION,
                description=policy.description,
            )
        )

    def write_baseline(self, baseline: ExpectedBaseline) -> ExpectedBaseline:
        from app.services.research_data.contracts import PerformanceExpectedBaselineSummary

        uri, cs = self._artifacts.write_baseline(baseline)
        pinned = baseline.model_copy(update={"storage_uri": uri})
        self._registry.upsert_performance_expected_baseline(
            PerformanceExpectedBaselineSummary(
                baseline_id=pinned.baseline_id,
                strategy_code=pinned.strategy_code,
                strategy_version=pinned.strategy_version,
                content_hash=pinned.content_hash,
                candidate_id=pinned.candidate_id,
                validation_id=pinned.validation_id,
                pipeline_run_id=pinned.pipeline_run_id,
                dataset_hash=pinned.dataset_hash,
                snapshot_id=pinned.snapshot_id,
                model_version=pinned.model_version,
                feature_version=pinned.feature_version,
                backtest_hash=pinned.backtest_hash,
                baseline_type=pinned.baseline_type,
                metrics_snapshot_json=pinned.metrics_snapshot.model_dump(mode="json"),
                drift_policy_id=pinned.drift_policy_id,
                drift_policy_version=pinned.drift_policy_version,
                drift_policy_content_hash=pinned.drift_policy_content_hash,
                immutable=pinned.immutable,
                created_at=pinned.created_at,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs},
            )
        )
        return pinned

    def write_run(self, run: PerformanceComparisonRun) -> PerformanceComparisonRun:
        from app.services.research_data.contracts import PerformanceComparisonRunSummary

        uri, cs = self._artifacts.write_run(run)
        completed = run.model_copy(update={"storage_uri": uri})
        self._registry.upsert_performance_comparison_run(
            PerformanceComparisonRunSummary(
                run_id=completed.run_id,
                strategy_code=completed.strategy_code,
                baseline_id=completed.baseline_id,
                actual_source=completed.actual_source,
                window_start=completed.window_start,
                window_end=completed.window_end,
                idempotency_key=completed.idempotency_key,
                status=completed.status,
                policy_id=completed.policy_id,
                policy_version=completed.policy_version,
                policy_content_hash=completed.policy_content_hash,
                actual_metrics_json=completed.actual_metrics.model_dump(mode="json"),
                deviation_json=[d.model_dump(mode="json") for d in completed.deviations],
                drift_findings_json=[f.model_dump(mode="json") for f in completed.findings],
                report_id=completed.report_id,
                started_at=completed.started_at,
                completed_at=completed.completed_at,
                storage_uri=uri,
                engine_version=ENGINE_VERSION,
                metadata={"checksum": cs},
            )
        )
        return completed

    def write_report_artifact(self, report: ProductionDriftReport) -> None:
        self._artifacts.write_report(report)


__all__ = ["PerformanceFeedbackWriter"]
