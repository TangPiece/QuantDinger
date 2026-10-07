"""Phase 8H：Experiment lineage 链接（parent_*；不跑训练）。"""

from __future__ import annotations

from datetime import datetime, timezone

from .identity import build_experiment_link_id
from .protocol import ENGINE_VERSION, FeedbackExperimentLink


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_experiment_link(
    *,
    experiment_id: str,
    strategy_code: str,
    feedback_dataset_id: str = "",
    failure_case_ids: list[str] | None = None,
    incident_ids: list[str] | None = None,
    hypothesis_id: str = "",
    session_id: str = "",
) -> FeedbackExperimentLink:
    ts = _now()
    link_id = build_experiment_link_id(experiment_id=experiment_id, created_at=ts)
    return FeedbackExperimentLink(
        link_id=link_id,
        experiment_id=str(experiment_id).strip(),
        strategy_code=str(strategy_code).strip(),
        parent_feedback_dataset_id=str(feedback_dataset_id or ""),
        parent_failure_case_ids=list(failure_case_ids or []),
        parent_incident_ids=list(incident_ids or []),
        hypothesis_id=str(hypothesis_id or ""),
        created_at=ts,
        session_id=session_id,
        engine_version=ENGINE_VERSION,
    )


__all__ = ["new_experiment_link"]
