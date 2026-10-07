"""Phase 8H：ProductionResearchFeedbackService 门面。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.services.research_data.registry import ResearchRegistry

from .builder import FeedbackBuilderError, build_production_feedback_dataset
from .collectors.inject import merge_feedback_inject
from .counterfactual import build_counterfactual_record, counterfactual_snapshot_stub
from .experiment_link import new_experiment_link
from .hypothesis import new_hypothesis
from .identity import build_failure_case_id, build_snapshot_id, normalize_session_id
from .pin import hash_reality_snapshot
from .protocol import (
    CounterfactualRecord,
    FeedbackExperimentLink,
    FeedbackType,
    PnlSummary,
    ProductionFeedbackDataset,
    ProductionRealitySnapshot,
    ResearchFailureCase,
    ResearchFeedbackQuery,
    ResearchFeedbackRecord,
    ResearchHypothesis,
)
from .quality_gate import QualityGateError
from .query import execute_feedback_query
from .writers import ProductionResearchFeedbackWriter, SnapshotImmutableError


class ProductionResearchFeedbackError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProductionResearchFeedbackService:
    """Production → Research Feedback（无自动训练 / 版本替换 / 交易库直读）。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        feedback_8e: Any | None = None,
        monitoring: Any | None = None,
        guardrails: Any | None = None,
        data_query: Any | None = None,
        writer: ProductionResearchFeedbackWriter | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._feedback_8e = feedback_8e
        self._monitoring = monitoring
        self._guardrails = guardrails
        self._data_query = data_query
        self._writer = writer or ProductionResearchFeedbackWriter(registry)

    def build_dataset(
        self,
        strategy_code: str,
        feedback_type: FeedbackType,
        window_start: str,
        window_end: str,
        *,
        inject: Mapping[str, Any] | None = None,
        session_id: str = "",
    ) -> ProductionFeedbackDataset:
        sid = normalize_session_id(session_id)
        try:
            ds = build_production_feedback_dataset(
                self._registry,
                strategy_code=strategy_code,
                feedback_type=feedback_type,
                window_start=window_start,
                window_end=window_end,
                inject=inject,
                feedback_8e=self._feedback_8e,
                monitoring=self._monitoring,
                guardrails=self._guardrails,
                session_id=sid,
            )
        except (FeedbackBuilderError, QualityGateError) as exc:
            raise ProductionResearchFeedbackError(str(exc)) from exc
        return self._writer.write_dataset(ds)

    def build_reality_snapshot(
        self,
        strategy_code: str,
        *,
        dataset_id: str = "",
        inject: Mapping[str, Any] | None = None,
        session_id: str = "",
        correction_of: str = "",
    ) -> ProductionRealitySnapshot:
        code = str(strategy_code or "").strip()
        sid = normalize_session_id(session_id)
        section = merge_feedback_inject(inject)
        as_of = str(section.get("as_of_time") or _now())
        pnl_total = float(section.get("pnl_total") or 0.0)
        metrics = {str(k): float(v) for k, v in dict(section.get("metrics") or {}).items()}
        snapshot_id = build_snapshot_id(strategy_code=code, as_of_time=as_of)
        snapshot_version = 1
        supersedes = ""
        if correction_of:
            try:
                prev = self._registry.get_production_reality_snapshot(correction_of)
            except KeyError as exc:
                raise ProductionResearchFeedbackError(f"correction target missing: {correction_of}") from exc
            snapshot_id = correction_of
            snapshot_version = int(prev.snapshot_version or 1) + 1
            supersedes = correction_of

        snap = ProductionRealitySnapshot(
            snapshot_id=snapshot_id,
            snapshot_version=snapshot_version,
            supersedes_snapshot_id=supersedes,
            strategy_code=code,
            reality_kind="ACTUAL",
            as_of_time=as_of,
            pnl_summary=PnlSummary(pnl_total=pnl_total, as_of_time=as_of),
            metrics=metrics,
            dataset_id=str(dataset_id or ""),
            created_at=_now(),
            session_id=sid,
        )
        snap = snap.model_copy(update={"content_hash": hash_reality_snapshot(snap)})
        try:
            return self._writer.write_snapshot(
                snap,
                allow_supersede=bool(correction_of),
            )
        except SnapshotImmutableError as exc:
            raise ProductionResearchFeedbackError(str(exc)) from exc

    def record_failure_case(
        self,
        strategy_code: str,
        *,
        incident_id: str = "",
        governance_decision_id: str = "",
        feedback_dataset_id: str = "",
        dataset_hash: str = "",
        summary: str = "",
        inject: Mapping[str, Any] | None = None,
        session_id: str = "",
    ) -> ResearchFailureCase:
        code = str(strategy_code or "").strip()
        sid = normalize_session_id(session_id)
        ts = _now()
        section = merge_feedback_inject(inject)
        case_id = build_failure_case_id(
            strategy_code=code,
            incident_id=incident_id or str(section.get("incident_id") or ""),
            created_at=ts,
        )
        from .protocol import FeedbackLineage

        lineage_raw = section.get("lineage") or {}
        lineage = (
            lineage_raw
            if isinstance(lineage_raw, FeedbackLineage)
            else FeedbackLineage.model_validate(lineage_raw)
        )
        case = ResearchFailureCase(
            case_id=case_id,
            strategy_code=code,
            incident_id=str(incident_id or section.get("incident_id") or lineage.incident_id or ""),
            governance_decision_id=str(
                governance_decision_id or section.get("governance_decision_id") or ""
            ),
            dataset_hash=str(dataset_hash or section.get("dataset_hash") or lineage.dataset_hash or ""),
            feedback_dataset_id=str(feedback_dataset_id or ""),
            summary=str(summary or section.get("summary") or ""),
            lineage=lineage,
            created_at=ts,
            session_id=sid,
        )
        return self._writer.write_failure_case(case)

    def query_feedback(self, query: ResearchFeedbackQuery) -> list[ResearchFeedbackRecord]:
        if self._data_query is not None and hasattr(self._data_query, "production_feedback"):
            return list(self._data_query.production_feedback(query))
        return execute_feedback_query(self._registry, query)

    def create_hypothesis(
        self,
        strategy_code: str,
        title: str,
        *,
        description: str = "",
        failure_case_ids: list[str] | None = None,
        feedback_dataset_id: str = "",
        session_id: str = "",
    ) -> ResearchHypothesis:
        hyp = new_hypothesis(
            strategy_code=strategy_code,
            title=title,
            description=description,
            failure_case_ids=failure_case_ids,
            feedback_dataset_id=feedback_dataset_id,
            session_id=normalize_session_id(session_id),
        )
        return self._writer.write_hypothesis(hyp)

    def link_experiment(
        self,
        experiment_id: str,
        *,
        feedback_dataset_id: str = "",
        failure_case_ids: list[str] | None = None,
        incident_ids: list[str] | None = None,
        strategy_code: str = "",
        hypothesis_id: str = "",
        session_id: str = "",
    ) -> FeedbackExperimentLink:
        link = new_experiment_link(
            experiment_id=experiment_id,
            strategy_code=strategy_code,
            feedback_dataset_id=feedback_dataset_id,
            failure_case_ids=failure_case_ids,
            incident_ids=incident_ids,
            hypothesis_id=hypothesis_id,
            session_id=normalize_session_id(session_id),
        )
        return self._writer.write_experiment_link(link)

    def build_counterfactual(
        self,
        snapshot_id: str,
        scenario: Mapping[str, Any],
        *,
        session_id: str = "",
    ) -> CounterfactualRecord:
        sid = normalize_session_id(session_id)
        try:
            record = build_counterfactual_record(
                self._registry,
                snapshot_id=snapshot_id,
                scenario=scenario,
                session_id=sid,
            )
        except Exception as exc:
            raise ProductionResearchFeedbackError(str(exc)) from exc
        record = self._writer.write_counterfactual(record)
        parent_row = self._registry.get_production_reality_snapshot(snapshot_id)
        parent = ProductionRealitySnapshot(
            snapshot_id=parent_row.snapshot_id,
            snapshot_version=parent_row.snapshot_version,
            strategy_code=parent_row.strategy_code,
            reality_kind="ACTUAL",
            as_of_time=parent_row.as_of_time or "",
            pnl_summary=PnlSummary(pnl_total=float(parent_row.pnl_total or 0.0)),
            metrics=dict(parent_row.metrics_json or {}),
            dataset_id=parent_row.dataset_id or "",
        )
        cf_snap = counterfactual_snapshot_stub(parent, record=record)
        self._writer.write_snapshot(cf_snap, allow_supersede=False)
        return record

    def get_dataset(self, dataset_id: str) -> ProductionFeedbackDataset:
        row = self._registry.get_production_feedback_dataset(dataset_id)
        from .protocol import FeedbackLineage, FeedbackRow

        return ProductionFeedbackDataset(
            dataset_id=row.dataset_id,
            strategy_code=row.strategy_code,
            feedback_type=row.feedback_type,  # type: ignore[arg-type]
            dataset_hash=row.dataset_hash,
            schema_version=row.schema_version,
            filter_spec=dict(row.filter_spec_json or {}),
            window_start=row.window_start or "",
            window_end=row.window_end or "",
            processor_id=row.processor_id,
            processor_version=row.processor_version,
            rows=[],
            lineage=FeedbackLineage.model_validate(row.lineage_json or {}),
            quality_gate_verdict=row.quality_gate_verdict,  # type: ignore[arg-type]
            storage_uri=row.storage_uri or "",
        )

    def list_failure_cases(self, strategy_code: str) -> list[ResearchFailureCase]:
        rows = self._registry.list_research_failure_cases(strategy_code)
        from .protocol import FeedbackLineage

        out: list[ResearchFailureCase] = []
        for row in rows:
            out.append(
                ResearchFailureCase(
                    case_id=row.case_id,
                    strategy_code=row.strategy_code,
                    incident_id=row.incident_id,
                    governance_decision_id=row.governance_decision_id,
                    dataset_hash=row.dataset_hash,
                    feedback_dataset_id=row.feedback_dataset_id,
                    category=row.category,
                    severity=row.severity,
                    summary=row.summary,
                    lineage=FeedbackLineage.model_validate(row.lineage_json or {}),
                    storage_uri=row.storage_uri or "",
                )
            )
        return out

    def get_snapshot(self, snapshot_id: str) -> ProductionRealitySnapshot:
        row = self._registry.get_production_reality_snapshot(snapshot_id)
        from .protocol import FeedbackLineage

        return ProductionRealitySnapshot(
            snapshot_id=row.snapshot_id,
            snapshot_version=row.snapshot_version,
            supersedes_snapshot_id=row.supersedes_snapshot_id or "",
            strategy_code=row.strategy_code,
            reality_kind=row.reality_kind,  # type: ignore[arg-type]
            as_of_time=row.as_of_time or "",
            pnl_summary=PnlSummary(pnl_total=float(row.pnl_total or 0.0), as_of_time=row.as_of_time or ""),
            metrics=dict(row.metrics_json or {}),
            dataset_id=row.dataset_id or "",
            content_hash=row.content_hash or "",
            lineage=FeedbackLineage.model_validate(row.lineage_json or {}),
            storage_uri=row.storage_uri or "",
        )


__all__ = [
    "ProductionResearchFeedbackError",
    "ProductionResearchFeedbackService",
]
