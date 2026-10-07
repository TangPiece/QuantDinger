"""Phase 8H：DataQuery 薄适配（只读 Registry；禁止 Trading DB）。"""

from __future__ import annotations

from app.services.research_data.registry import ResearchRegistry

from .protocol import ResearchFeedbackQuery, ResearchFeedbackRecord
from .query import execute_feedback_query


def query_production_feedback(
    registry: ResearchRegistry,
    query: ResearchFeedbackQuery,
) -> list[ResearchFeedbackRecord]:
    return execute_feedback_query(registry, query)


__all__ = ["query_production_feedback"]
