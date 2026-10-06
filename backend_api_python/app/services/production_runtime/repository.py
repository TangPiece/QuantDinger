"""Production Runtime Repository 协议（薄包装 registry）。"""

from __future__ import annotations

from typing import Protocol

from app.services.research_data.contracts import (
    ProductionRuntimeEventRecord,
    ProductionRuntimeRunSummary,
    ProductionRuntimeSummary,
)


class ProductionRuntimeRepository(Protocol):
    def upsert_production_runtime(self, record: ProductionRuntimeSummary) -> None: ...

    def get_production_runtime(self, runtime_id: str) -> ProductionRuntimeSummary: ...

    def append_runtime_event(self, record: ProductionRuntimeEventRecord) -> None: ...

    def list_runtime_events(
        self, runtime_id: str, *, limit: int = 200
    ) -> list[ProductionRuntimeEventRecord]: ...

    def upsert_runtime_run(self, record: ProductionRuntimeRunSummary) -> None: ...

    def get_runtime_run_by_idempotency(
        self, idempotency_key: str
    ) -> ProductionRuntimeRunSummary: ...

    def get_runtime_run(self, run_id: str) -> ProductionRuntimeRunSummary: ...
