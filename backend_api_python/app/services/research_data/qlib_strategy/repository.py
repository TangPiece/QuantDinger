"""Qlib Run Registry Protocol。"""

from __future__ import annotations

from typing import Protocol

from app.services.research_data.contracts import QlibRunSummary


class QlibRunRepository(Protocol):
    def upsert_research_qlib_run(self, record: QlibRunSummary) -> None: ...

    def get_research_qlib_run(self, qlib_run_hash: str) -> QlibRunSummary: ...
