"""Research Backtest Registry Protocol。"""

from __future__ import annotations

from typing import Protocol

from app.services.research_data.contracts import ResearchBacktestSummary


class ResearchBacktestRepository(Protocol):
    """D1/Local：仅 Summary，无日明细。"""

    def upsert_research_backtest(self, record: ResearchBacktestSummary) -> None: ...

    def get_research_backtest(self, backtest_hash: str) -> ResearchBacktestSummary: ...
