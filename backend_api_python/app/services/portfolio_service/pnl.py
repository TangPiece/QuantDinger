"""P&L：realized / unrealized / fees → total。"""

from __future__ import annotations

from typing import Mapping

from .protocol import Account, PnL, Position, PortfolioState


def mark_to_market(
    state: PortfolioState,
    prices: Mapping[str, float],
) -> PortfolioState:
    """按 as-of 价格更新 market_value 与 unrealized_pnl。"""
    mv_total = 0.0
    unreal = 0.0
    for key, pos in list(state.positions.items()):
        px = float(prices.get(key) or 0.0)
        mv = float(pos.quantity) * px
        u = (px - float(pos.avg_cost)) * float(pos.quantity) if px else 0.0
        state.positions[key] = pos.model_copy(update={"market_value": mv})
        mv_total += mv
        unreal += u
    pnl = state.account.pnl.model_copy(update={"unrealized_pnl": unreal})
    acct = state.account.model_copy(
        update={"market_value": mv_total, "pnl": pnl}
    ).recompute_equity()
    # total_pnl 口径
    total = (
        float(pnl.realized_pnl)
        + float(pnl.unrealized_pnl)
        - float(pnl.fees)
        - float(pnl.slippage)
        - float(pnl.funding_tax)
    )
    # 把 total 写入 metadata 便于 snapshot（PnL.total_pnl 是 property）
    meta = dict(acct.metadata or {})
    meta["total_pnl"] = total
    state.account = acct.model_copy(update={"metadata": meta})
    return state


def pnl_from_account(account: Account) -> PnL:
    return account.pnl


def compute_total_pnl(pnl: PnL) -> float:
    return float(pnl.total_pnl)
