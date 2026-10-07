"""Phase 8H：Feedback Builder（采集 → QualityGate → 不可变 Dataset）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.services.research_data.registry import ResearchRegistry

from .collectors import (
    collect_from_inject,
    merge_feedback_inject,
)
from .bridges.registry_artifacts import load_registry_feedback_context
from .hashing import compute_feedback_dataset_hash
from .protocol import (
    ENGINE_VERSION,
    FeedbackRow,
    FeedbackType,
    ProductionFeedbackDataset,
)
from .quality_gate import assert_quality_gate, evaluate_feedback_rows, gate_from_inject
from .identity import build_dataset_id


class FeedbackBuilderError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_production_feedback_dataset(
    registry: ResearchRegistry,
    *,
    strategy_code: str,
    feedback_type: FeedbackType,
    window_start: str,
    window_end: str,
    inject: Mapping[str, Any] | None = None,
    feedback_8e: Any | None = None,
    monitoring: Any | None = None,
    guardrails: Any | None = None,
    session_id: str = "",
    schema_version: str = "pf_schema@1",
    processor_id: str = "pf_processor@1",
    processor_version: str = "1",
) -> ProductionFeedbackDataset:
    code = str(strategy_code or "").strip()
    if not code:
        raise FeedbackBuilderError("strategy_code required")
    section = merge_feedback_inject(inject)
    if section:
        inj_rows, inj_lineage, extras = collect_from_inject(section)
    else:
        inj_rows, inj_lineage, extras = [], None, {}
    bridge_rows, bridge_lineage = load_registry_feedback_context(
        registry,
        strategy_code=code,
        feedback_8e=feedback_8e,
        monitoring=monitoring,
        guardrails=guardrails,
    )
    rows: list[FeedbackRow] = list(inj_rows) + list(bridge_rows)
    lineage = inj_lineage if inj_lineage is not None else bridge_lineage
    if inj_lineage is not None:
        for field in (
            "comparison_run_id",
            "drift_report_id",
            "alert_id",
            "incident_id",
            "governance_decision_id",
            "dataset_hash",
            "snapshot_id",
            "model_version",
            "strategy_version",
        ):
            val = getattr(inj_lineage, field, "")
            if val:
                lineage = lineage.model_copy(update={field: val})

    filter_spec = dict(extras.get("filter_spec") or {})
    gate_inject = gate_from_inject(section)
    if gate_inject.verdict == "REJECT":
        assert_quality_gate(gate_inject)

    pnl_total = extras.get("pnl_total")
    qg = evaluate_feedback_rows(
        rows,
        lineage=lineage,
        pnl_total=float(pnl_total) if pnl_total is not None else None,
        require_pit=bool(section) or bool(rows),
    )
    assert_quality_gate(qg)

    ds_hash = compute_feedback_dataset_hash(
        strategy_code=code,
        feedback_type=feedback_type,
        schema_version=schema_version,
        filter_spec=filter_spec,
        window_start=window_start,
        window_end=window_end,
        processor_id=processor_id,
        processor_version=processor_version,
        rows=rows,
    )
    dataset_id = build_dataset_id(
        strategy_code=code,
        feedback_type=feedback_type,
        window_start=window_start,
        window_end=window_end,
    )
    return ProductionFeedbackDataset(
        dataset_id=dataset_id,
        strategy_code=code,
        feedback_type=feedback_type,
        dataset_hash=ds_hash,
        schema_version=schema_version,
        filter_spec=filter_spec,
        window_start=window_start,
        window_end=window_end,
        processor_id=processor_id,
        processor_version=processor_version,
        rows=rows,
        lineage=lineage,
        quality_gate_verdict="PASS",
        created_at=_now(),
        session_id=session_id,
        engine_version=ENGINE_VERSION,
    )


__all__ = ["FeedbackBuilderError", "build_production_feedback_dataset"]
