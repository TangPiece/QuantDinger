"""极简 PAPER Fill：按 as-of 价即时全成（无滑点/部分成交）。"""

from __future__ import annotations

from typing import Mapping, Sequence

from .events import make_event
from .protocol import PositionDelta, PositionEvent, PortfolioState

# 默认佣金/印花税 stub（bps）
_DEFAULT_COMMISSION_BPS = 3.0
_DEFAULT_STAMP_BPS = 5.0  # 仅卖出


def simulate_fills(
    state: PortfolioState,
    deltas: Sequence[PositionDelta],
    prices: Mapping[str, float],
    *,
    trading_date: str = "",
    idempotency_key: str = "",
    commission_bps: float = _DEFAULT_COMMISSION_BPS,
    stamp_bps: float = _DEFAULT_STAMP_BPS,
) -> list[PositionEvent]:
    """PositionDelta → BUY_FILLED / SELL_FILLED 事件。"""
    events: list[PositionEvent] = []
    for i, d in enumerate(deltas):
        if d.side == "FLAT" or abs(float(d.delta_quantity)) < 1e-12:
            continue
        key = d.instrument_key
        px = float(prices.get(key) or 0.0)
        if px <= 0:
            continue
        qty = abs(float(d.delta_quantity))
        notional = qty * px
        if d.side == "BUY":
            fee = notional * (commission_bps / 10_000.0)
            events.append(
                make_event(
                    portfolio_id=state.portfolio.portfolio_id,
                    account_id=state.account.account_id,
                    event_type="BUY_FILLED",
                    instrument_key=key,
                    trading_date=trading_date,
                    quantity=qty,
                    price=px,
                    cash_delta=-(notional + fee),
                    fee=fee,
                    idempotency_key=idempotency_key,
                    message=f"paper buy {qty}@{px}",
                    salt=f"fill|BUY|{key}|{trading_date}|{i}|{idempotency_key[:8]}",
                )
            )
        elif d.side == "SELL":
            fee = notional * ((commission_bps + stamp_bps) / 10_000.0)
            events.append(
                make_event(
                    portfolio_id=state.portfolio.portfolio_id,
                    account_id=state.account.account_id,
                    event_type="SELL_FILLED",
                    instrument_key=key,
                    trading_date=trading_date,
                    quantity=qty,
                    price=px,
                    cash_delta=notional - fee,
                    fee=fee,
                    idempotency_key=idempotency_key,
                    message=f"paper sell {qty}@{px}",
                    salt=f"fill|SELL|{key}|{trading_date}|{i}|{idempotency_key[:8]}",
                )
            )
    return events


class PaperFillSimulator:
    """PAPER 默认撮合器。"""

    def __init__(
        self,
        *,
        commission_bps: float = _DEFAULT_COMMISSION_BPS,
        stamp_bps: float = _DEFAULT_STAMP_BPS,
    ) -> None:
        self.commission_bps = commission_bps
        self.stamp_bps = stamp_bps

    def fill(
        self,
        state: PortfolioState,
        deltas: Sequence[PositionDelta],
        prices: Mapping[str, float],
        *,
        trading_date: str = "",
        idempotency_key: str = "",
    ) -> list[PositionEvent]:
        return simulate_fills(
            state,
            deltas,
            prices,
            trading_date=trading_date,
            idempotency_key=idempotency_key,
            commission_bps=self.commission_bps,
            stamp_bps=self.stamp_bps,
        )
