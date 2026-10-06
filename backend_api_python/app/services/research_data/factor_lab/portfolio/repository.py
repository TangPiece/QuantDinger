"""FactorPortfolioSummary Repository 接口。"""

from __future__ import annotations

from typing import Protocol

from app.services.research_data.contracts import FactorPortfolioSummary


class FactorPortfolioSummaryRepository(Protocol):
    def upsert_factor_portfolio(self, record: FactorPortfolioSummary) -> None: ...

    def get_factor_portfolio(self, portfolio_hash: str) -> FactorPortfolioSummary: ...
