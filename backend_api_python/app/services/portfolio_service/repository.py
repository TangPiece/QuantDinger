"""Portfolio Repository 协议。"""

from __future__ import annotations

from typing import Protocol

from app.services.research_data.contracts import (
    ProductionAccountSummary,
    ProductionPortfolioApplySummary,
    ProductionPortfolioSnapshotSummary,
    ProductionPortfolioSummary,
    ProductionPositionEventRecord,
    ProductionPositionSummary,
)


class PortfolioRepository(Protocol):
    def upsert_production_account(self, record: ProductionAccountSummary) -> None: ...

    def get_production_account(self, account_id: str) -> ProductionAccountSummary: ...

    def upsert_production_portfolio(
        self, record: ProductionPortfolioSummary
    ) -> None: ...

    def get_production_portfolio(
        self, portfolio_id: str
    ) -> ProductionPortfolioSummary: ...

    def list_portfolios_by_account(
        self, account_id: str
    ) -> list[ProductionPortfolioSummary]: ...

    def upsert_production_position(
        self, record: ProductionPositionSummary
    ) -> None: ...

    def list_positions(
        self, portfolio_id: str
    ) -> list[ProductionPositionSummary]: ...

    def append_position_event(
        self, record: ProductionPositionEventRecord
    ) -> None: ...

    def list_position_events(
        self, portfolio_id: str, *, limit: int = 500
    ) -> list[ProductionPositionEventRecord]: ...

    def upsert_portfolio_snapshot(
        self, record: ProductionPortfolioSnapshotSummary
    ) -> None: ...

    def get_portfolio_snapshot(
        self, snapshot_id: str
    ) -> ProductionPortfolioSnapshotSummary: ...

    def upsert_portfolio_apply(
        self, record: ProductionPortfolioApplySummary
    ) -> None: ...

    def get_apply_by_idempotency(
        self, idempotency_key: str
    ) -> ProductionPortfolioApplySummary: ...
