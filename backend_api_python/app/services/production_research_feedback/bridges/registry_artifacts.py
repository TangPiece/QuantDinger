"""Phase 8H：聚合 8E/8F/8G registry 上下文（只读）。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.registry import ResearchRegistry

from ..collectors.from_feedback_8e import collect_from_feedback_8e
from ..collectors.from_guardrails_8g import collect_from_guardrails_8g
from ..collectors.from_monitoring_8f import collect_from_monitoring_8f
from ..protocol import FeedbackLineage, FeedbackRow


def load_registry_feedback_context(
    registry: ResearchRegistry,
    *,
    strategy_code: str,
    feedback_8e: Any | None = None,
    monitoring: Any | None = None,
    guardrails: Any | None = None,
) -> tuple[list[FeedbackRow], FeedbackLineage]:
    rows: list[FeedbackRow] = []
    lineage = FeedbackLineage()
    for collector in (
        lambda: collect_from_feedback_8e(registry, strategy_code=strategy_code, feedback_8e=feedback_8e),
        lambda: collect_from_monitoring_8f(registry, strategy_code=strategy_code, monitoring=monitoring),
        lambda: collect_from_guardrails_8g(registry, strategy_code=strategy_code, guardrails=guardrails),
    ):
        part_rows, part_lin = collector()
        rows.extend(part_rows)
        if part_lin.incident_id and not lineage.incident_id:
            lineage = lineage.model_copy(update={"incident_id": part_lin.incident_id})
        if part_lin.alert_id and not lineage.alert_id:
            lineage = lineage.model_copy(update={"alert_id": part_lin.alert_id})
        if part_lin.comparison_run_id and not lineage.comparison_run_id:
            lineage = lineage.model_copy(update={"comparison_run_id": part_lin.comparison_run_id})
    return rows, lineage


__all__ = ["load_registry_feedback_context"]
