"""CrossValidation Registry 协议。"""

from __future__ import annotations

from typing import Protocol

from app.services.research_data.contracts import CrossValidationSummary


class CrossValidationRepository(Protocol):
    def upsert_research_cross_validation(
        self, record: CrossValidationSummary
    ) -> None: ...

    def get_research_cross_validation(self, cv_hash: str) -> CrossValidationSummary: ...
