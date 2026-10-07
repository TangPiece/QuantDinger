"""Phase 8H：从 8F Strategy Monitoring registry 工件只读采集。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.registry import ResearchRegistry

from ..protocol import FeedbackLineage, FeedbackRow


def collect_from_monitoring_8f(
    registry: ResearchRegistry,
    *,
    strategy_code: str,
    monitoring: Any | None = None,
) -> tuple[list[FeedbackRow], FeedbackLineage]:
    rows: list[FeedbackRow] = []
    lineage = FeedbackLineage()
    code = str(strategy_code or "").strip()
    try:
        alerts = registry.list_strategy_alerts(code)
    except Exception:
        alerts = []
    if alerts:
        alert = alerts[-1]
        lineage = FeedbackLineage(alert_id=alert.alert_id)
        rows.append(
            FeedbackRow(
                row_id=f"8f_{alert.alert_id}",
                metric=str(alert.category or "alert"),
                value=1.0,
                as_of_time=alert.last_seen_at or alert.first_seen_at or "",
                source_artifact_id=alert.alert_id,
                source_phase="8F",
            )
        )
    del monitoring
    return rows, lineage
