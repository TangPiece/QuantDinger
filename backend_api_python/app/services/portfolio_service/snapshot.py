"""Snapshot 构建与从 snapshot + tail events 恢复。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .exposure import compute_exposure
from .hash import compute_snapshot_id
from .protocol import (
    Account,
    CashBalance,
    Exposure,
    PnL,
    Portfolio,
    PortfolioSnapshot,
    PortfolioState,
    Position,
    PositionEvent,
    PositionSnapshot,
)
from .reducer import apply_events, assert_invariants


def build_snapshot(
    state: PortfolioState,
    *,
    trading_date: str,
    knowledge_time: str | None = None,
    runtime_id: str = "",
    bundle_hash: str = "",
    turnover: float = 0.0,
    storage_uri: str = "",
    metadata: dict[str, Any] | None = None,
) -> PortfolioSnapshot:
    """从当前态生成 PortfolioSnapshot。"""
    acct = state.account
    exp = compute_exposure(state.positions, equity=float(acct.equity))
    eq = float(acct.equity) or 1.0
    pos_snaps: list[PositionSnapshot] = []
    for key, pos in sorted(state.positions.items()):
        w = float(pos.market_value) / eq if eq else 0.0
        u = (float(pos.market_value) - float(pos.avg_cost) * float(pos.quantity))
        pos_snaps.append(
            PositionSnapshot(
                instrument_key=key,
                trading_date=trading_date,
                quantity=float(pos.quantity),
                available_quantity=float(pos.available_quantity),
                frozen_quantity=float(pos.frozen_quantity),
                avg_cost=float(pos.avg_cost),
                market_value=float(pos.market_value),
                weight=w,
                unrealized_pnl=u,
            )
        )
    kt = knowledge_time or datetime.now(timezone.utc).isoformat()
    sid = compute_snapshot_id(
        portfolio_id=state.portfolio.portfolio_id,
        trading_date=trading_date,
        knowledge_time=kt,
    )
    total = float(acct.metadata.get("total_pnl") or acct.pnl.total_pnl)
    return PortfolioSnapshot(
        snapshot_id=sid,
        account_id=acct.account_id,
        portfolio_id=state.portfolio.portfolio_id,
        trading_date=trading_date,
        knowledge_time=kt,
        cash=float(acct.cash.cash),
        available_cash=float(acct.cash.available_cash),
        frozen_cash=float(acct.cash.frozen_cash),
        market_value=float(acct.market_value),
        equity=float(acct.equity),
        realized_pnl=float(acct.pnl.realized_pnl),
        unrealized_pnl=float(acct.pnl.unrealized_pnl),
        total_pnl=total,
        fees=float(acct.pnl.fees),
        gross_exposure=exp.gross_exposure,
        net_exposure=exp.net_exposure,
        turnover=turnover,
        runtime_id=runtime_id or state.portfolio.runtime_id,
        bundle_hash=bundle_hash or state.portfolio.bundle_hash,
        positions=pos_snaps,
        exposure=exp,
        storage_uri=storage_uri,
        metadata=dict(metadata or {}),
    )


def state_from_snapshot(
    snapshot: PortfolioSnapshot,
    *,
    account: Account | None = None,
    portfolio: Portfolio | None = None,
) -> PortfolioState:
    """从快照恢复 PortfolioState（不含后续事件）。"""
    acct = account or Account(
        account_id=snapshot.account_id,
        cash=CashBalance(
            available_cash=float(snapshot.available_cash),
            frozen_cash=float(snapshot.frozen_cash),
        ),
        market_value=float(snapshot.market_value),
        equity=float(snapshot.equity),
        pnl=PnL(
            realized_pnl=float(snapshot.realized_pnl),
            unrealized_pnl=float(snapshot.unrealized_pnl),
            fees=float(snapshot.fees),
        ),
        exposure=snapshot.exposure or Exposure(),
        metadata={"total_pnl": snapshot.total_pnl},
    )
    pf = portfolio or Portfolio(
        portfolio_id=snapshot.portfolio_id,
        account_id=snapshot.account_id,
        runtime_id=snapshot.runtime_id,
        bundle_hash=snapshot.bundle_hash,
        trading_date=snapshot.trading_date,
    )
    positions: dict[str, Position] = {}
    for ps in snapshot.positions:
        positions[ps.instrument_key] = Position(
            instrument_key=ps.instrument_key,
            quantity=float(ps.quantity),
            available_quantity=float(ps.available_quantity),
            frozen_quantity=float(ps.frozen_quantity),
            avg_cost=float(ps.avg_cost),
            market_value=float(ps.market_value),
            as_of=ps.trading_date,
        )
    return PortfolioState(account=acct, portfolio=pf, positions=positions)


def recover(
    snapshot: PortfolioSnapshot,
    tail_events: Sequence[PositionEvent],
    *,
    account: Account | None = None,
    portfolio: Portfolio | None = None,
) -> PortfolioState:
    """Latest Snapshot + replay subsequent events。"""
    state = state_from_snapshot(snapshot, account=account, portfolio=portfolio)
    apply_events(state, tail_events)
    assert_invariants(state)
    return state
