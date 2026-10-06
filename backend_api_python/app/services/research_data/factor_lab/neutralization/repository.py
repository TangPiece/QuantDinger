"""FactorNeutralizationSummary Repository 接口。"""

from __future__ import annotations

from typing import Protocol

from app.services.research_data.contracts import FactorNeutralizationSummary


class FactorNeutralizationSummaryRepository(Protocol):
    def upsert_factor_neutralization(
        self, record: FactorNeutralizationSummary
    ) -> None: ...

    def get_factor_neutralization(
        self, neutralization_hash: str
    ) -> FactorNeutralizationSummary: ...
