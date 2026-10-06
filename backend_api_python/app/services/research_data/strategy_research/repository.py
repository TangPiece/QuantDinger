"""Strategy Research Registry 接口。"""

from __future__ import annotations

from typing import Protocol

from app.services.research_data.contracts import (
    ResearchStrategyRecord,
    StrategyResearchSummary,
)


class StrategyResearchRepository(Protocol):
    def upsert_research_strategy(self, record: ResearchStrategyRecord) -> None: ...

    def get_research_strategy(self, strategy_code: str) -> ResearchStrategyRecord: ...

    def upsert_strategy_research(self, record: StrategyResearchSummary) -> None: ...

    def get_strategy_research(self, strategy_hash: str) -> StrategyResearchSummary: ...
