"""Group Repository Protocols（无 R2/D1/Polars/DuckDB/Qlib SDK）。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.services.research_data.contracts import GroupEvaluationSummary

from .protocol import GroupManifest


@runtime_checkable
class GroupEvaluationSummaryRepository(Protocol):
    def upsert_factor_group_evaluation(
        self, record: GroupEvaluationSummary
    ) -> None: ...

    def get_factor_group_evaluation(
        self, group_evaluation_hash: str, horizon: int
    ) -> GroupEvaluationSummary: ...


@runtime_checkable
class GroupManifestRepository(Protocol):
    def write_manifest(self, manifest: GroupManifest) -> str: ...

    def read_manifest(self, group_evaluation_hash: str) -> GroupManifest: ...
