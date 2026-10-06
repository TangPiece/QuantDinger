"""FactorCombinationSummary Repository 接口。"""

from __future__ import annotations

from typing import Protocol

from app.services.research_data.contracts import FactorCombinationSummary


class FactorCombinationSummaryRepository(Protocol):
    def upsert_factor_combination(
        self, record: FactorCombinationSummary
    ) -> None: ...

    def get_factor_combination(
        self, combination_hash: str
    ) -> FactorCombinationSummary: ...
