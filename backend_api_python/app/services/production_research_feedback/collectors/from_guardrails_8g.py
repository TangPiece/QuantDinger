"""Phase 8H：从 8G Guardrails registry 工件只读采集。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.registry import ResearchRegistry

from ..protocol import FeedbackLineage, FeedbackRow


def collect_from_guardrails_8g(
    registry: ResearchRegistry,
    *,
    strategy_code: str,
    guardrails: Any | None = None,
) -> tuple[list[FeedbackRow], FeedbackLineage]:
    rows: list[FeedbackRow] = []
    lineage = FeedbackLineage()
    code = str(strategy_code or "").strip()
    try:
        incidents = registry.list_governance_incidents(code)
    except Exception:
        incidents = []
    if incidents:
        inc = incidents[-1]
        lineage = FeedbackLineage(
            incident_id=inc.incident_id,
            dataset_hash=inc.metadata.get("dataset_hash", "") if inc.metadata else "",
        )
        rows.append(
            FeedbackRow(
                row_id=f"8g_{inc.incident_id}",
                metric=str(inc.category or "incident"),
                value=1.0,
                as_of_time=inc.opened_at or "",
                source_artifact_id=inc.incident_id,
                source_phase="8G",
            )
        )
    del guardrails
    return rows, lineage
