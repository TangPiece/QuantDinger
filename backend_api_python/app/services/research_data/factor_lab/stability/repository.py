"""FactorStabilitySummary Repository 接口。"""

from __future__ import annotations

from typing import Protocol

from app.services.research_data.contracts import FactorStabilitySummary


class FactorStabilitySummaryRepository(Protocol):
    def upsert_factor_stability_evaluation(
        self, record: FactorStabilitySummary
    ) -> None: ...

    def get_factor_stability_evaluation(
        self, stability_hash: str, horizon: int
    ) -> FactorStabilitySummary: ...
