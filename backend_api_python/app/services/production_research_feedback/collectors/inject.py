"""Phase 8H：Fake production inject（Golden / verify）。"""

from __future__ import annotations

from typing import Any, Mapping

from ..protocol import FeedbackLineage, FeedbackRow


def merge_feedback_inject(inject: Mapping[str, Any] | None) -> dict[str, Any]:
    if not inject:
        return {}
    section = inject.get("production_feedback")
    if isinstance(section, dict):
        return dict(section)
    return {}


def collect_from_inject(section: Mapping[str, Any]) -> tuple[list[FeedbackRow], FeedbackLineage, dict[str, Any]]:
    rows_raw = section.get("rows") or []
    rows: list[FeedbackRow] = []
    for i, raw in enumerate(rows_raw):
        if isinstance(raw, FeedbackRow):
            rows.append(raw)
        elif isinstance(raw, dict):
            rows.append(FeedbackRow.model_validate({**raw, "row_id": raw.get("row_id") or f"inj_{i}"}))
    lineage_raw = section.get("lineage") or {}
    lineage = (
        lineage_raw
        if isinstance(lineage_raw, FeedbackLineage)
        else FeedbackLineage.model_validate(lineage_raw)
    )
    extras = {
        "as_of_time": str(section.get("as_of_time") or ""),
        "pnl_total": section.get("pnl_total"),
        "metrics": dict(section.get("metrics") or {}),
        "filter_spec": dict(section.get("filter_spec") or {}),
    }
    return rows, lineage, extras


__all__ = ["collect_from_inject", "merge_feedback_inject"]
