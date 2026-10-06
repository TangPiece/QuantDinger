"""Account / Portfolio / Position / Snapshot → Registry + Artifact。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.contracts import (
    ProductionAccountSummary,
    ProductionPortfolioApplySummary,
    ProductionPortfolioSnapshotSummary,
    ProductionPortfolioSummary,
    ProductionPositionEventRecord,
    ProductionPositionSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import PortfolioArtifactStore
from .protocol import (
    ENGINE_VERSION,
    Account,
    ApplyTargetsResult,
    Portfolio,
    PortfolioSnapshot,
    PortfolioState,
    Position,
    PositionEvent,
)


class PortfolioWriter:
    """写生产组合状态。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: PortfolioArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or PortfolioArtifactStore()

    def write_account(self, account: Account) -> ProductionAccountSummary:
        summary = ProductionAccountSummary(
            account_id=account.account_id,
            environment=account.environment,
            market=account.market,
            status=account.status,
            currency=account.currency,
            available_cash=float(account.cash.available_cash),
            frozen_cash=float(account.cash.frozen_cash),
            market_value=float(account.market_value),
            equity=float(account.equity),
            realized_pnl=float(account.pnl.realized_pnl),
            unrealized_pnl=float(account.pnl.unrealized_pnl),
            total_pnl=float(account.pnl.total_pnl),
            engine_version=account.engine_version or ENGINE_VERSION,
            storage_uri=account.storage_uri,
            created_at=account.created_at,
            metadata=dict(account.metadata or {}),
        )
        self._registry.upsert_production_account(summary)
        return summary

    def write_portfolio(self, portfolio: Portfolio) -> ProductionPortfolioSummary:
        summary = ProductionPortfolioSummary(
            portfolio_id=portfolio.portfolio_id,
            account_id=portfolio.account_id,
            runtime_id=portfolio.runtime_id,
            bundle_hash=portfolio.bundle_hash,
            status=portfolio.status,
            trading_date=portfolio.trading_date,
            engine_version=portfolio.engine_version or ENGINE_VERSION,
            storage_uri=portfolio.storage_uri,
            created_at=portfolio.created_at,
            metadata=dict(portfolio.metadata or {}),
        )
        self._registry.upsert_production_portfolio(summary)
        return summary

    def write_positions(
        self, portfolio_id: str, positions: dict[str, Position] | list[Position]
    ) -> None:
        items = (
            positions.values() if isinstance(positions, dict) else positions
        )
        for pos in items:
            rec = ProductionPositionSummary(
                portfolio_id=portfolio_id,
                instrument_key=pos.instrument_key,
                quantity=float(pos.quantity),
                available_quantity=float(pos.available_quantity),
                frozen_quantity=float(pos.frozen_quantity),
                avg_cost=float(pos.avg_cost),
                market_value=float(pos.market_value),
                currency=pos.currency,
                as_of=pos.as_of,
                metadata=dict(pos.metadata or {}),
            )
            self._registry.upsert_production_position(rec)

    def write_event(self, event: PositionEvent) -> None:
        rec = ProductionPositionEventRecord(
            event_id=event.event_id,
            portfolio_id=event.portfolio_id,
            account_id=event.account_id,
            event_type=str(event.event_type),
            instrument_key=event.instrument_key,
            trading_date=event.trading_date,
            quantity=float(event.quantity),
            price=float(event.price),
            cash_delta=float(event.cash_delta),
            fee=float(event.fee),
            idempotency_key=event.idempotency_key,
            message=event.message,
            payload_json=dict(event.payload or {}),
            created_at=event.created_at,
        )
        self._registry.append_position_event(rec)
        try:
            self._artifacts.write_event(event.account_id or "unknown", event)
        except Exception:
            pass

    def write_snapshot(
        self, snapshot: PortfolioSnapshot, *, idempotency_key: str = ""
    ) -> ProductionPortfolioSnapshotSummary:
        uri = self._artifacts.write_snapshot(snapshot)
        summary = ProductionPortfolioSnapshotSummary(
            snapshot_id=snapshot.snapshot_id,
            account_id=snapshot.account_id,
            portfolio_id=snapshot.portfolio_id,
            trading_date=snapshot.trading_date,
            knowledge_time=snapshot.knowledge_time,
            cash=float(snapshot.cash),
            market_value=float(snapshot.market_value),
            equity=float(snapshot.equity),
            realized_pnl=float(snapshot.realized_pnl),
            unrealized_pnl=float(snapshot.unrealized_pnl),
            total_pnl=float(snapshot.total_pnl),
            gross_exposure=float(snapshot.gross_exposure),
            net_exposure=float(snapshot.net_exposure),
            runtime_id=snapshot.runtime_id,
            bundle_hash=snapshot.bundle_hash,
            idempotency_key=idempotency_key,
            storage_uri=uri,
            metadata=dict(snapshot.metadata or {}),
        )
        self._registry.upsert_portfolio_snapshot(summary)
        return summary

    def write_apply(self, result: ApplyTargetsResult) -> ProductionPortfolioApplySummary:
        rec = ProductionPortfolioApplySummary(
            apply_id=result.apply_id,
            account_id=result.account_id,
            portfolio_id=result.portfolio_id,
            idempotency_key=result.idempotency_key,
            trading_date=result.trading_date,
            status=result.status,
            n_deltas=len(result.deltas),
            n_events=len(result.events),
            snapshot_id=result.snapshot_id,
            runtime_id=str((result.metadata or {}).get("runtime_id") or ""),
            run_id=str((result.metadata or {}).get("run_id") or ""),
            storage_uri=(
                result.snapshot.storage_uri if result.snapshot else ""
            ),
            metadata=dict(result.metadata or {}),
        )
        self._registry.upsert_portfolio_apply(rec)
        return rec

    def persist_state(self, state: PortfolioState) -> None:
        self.write_account(state.account)
        self.write_portfolio(state.portfolio)
        self.write_positions(state.portfolio.portfolio_id, state.positions)
