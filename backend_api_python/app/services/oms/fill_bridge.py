"""Fill → 6B PositionEvent（卖先 FREEZE，成交后再 UNFREEZE）。"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from app.services.portfolio_service.events import make_event
from app.services.portfolio_service.protocol import PositionEvent
from app.services.portfolio_service.writers import PortfolioWriter

from .protocol import Fill, Order

_DEFAULT_COMMISSION_BPS = 3.0
_DEFAULT_STAMP_BPS = 5.0


def fills_to_position_events(
    order: Order,
    fills: Sequence[Fill],
    *,
    commission_bps: float = _DEFAULT_COMMISSION_BPS,
    stamp_bps: float = _DEFAULT_STAMP_BPS,
) -> list[PositionEvent]:
    """构造 FREEZE → BUY/SELL_FILLED → UNFREEZE 事件链。"""
    events: list[PositionEvent] = []
    pid = order.portfolio_id
    aid = order.account_id
    if not pid or not aid:
        return events

    for i, fill in enumerate(fills):
        qty = float(fill.quantity)
        px = float(fill.price)
        if qty <= 0 or px <= 0:
            continue
        notional = qty * px
        key = fill.instrument_key or order.instrument_key
        td = fill.trading_date or order.trading_date
        idem = f"oms|{order.order_id}|{fill.fill_id}"

        if str(order.side) == "SELL":
            # 卖出：FREEZE → SELL_FILLED（成交扣减 frozen；无需再 UNFREEZE）
            events.append(
                make_event(
                    portfolio_id=pid,
                    account_id=aid,
                    event_type="FREEZE",
                    instrument_key=key,
                    trading_date=td,
                    quantity=qty,
                    price=px,
                    idempotency_key=idem,
                    message=f"oms freeze for sell {order.order_id}",
                    payload={"order_id": order.order_id, "fill_id": fill.fill_id},
                    salt=f"freeze|{fill.fill_id}|{i}",
                )
            )
            fee = notional * ((commission_bps + stamp_bps) / 10_000.0)
            events.append(
                make_event(
                    portfolio_id=pid,
                    account_id=aid,
                    event_type="SELL_FILLED",
                    instrument_key=key,
                    trading_date=td,
                    quantity=qty,
                    price=px,
                    cash_delta=notional - fee,
                    fee=fee,
                    idempotency_key=idem,
                    message=f"oms sell fill {qty}@{px}",
                    payload={"order_id": order.order_id, "fill_id": fill.fill_id},
                    salt=f"sell|{fill.fill_id}|{i}",
                )
            )
        else:
            fee = notional * (commission_bps / 10_000.0)
            events.append(
                make_event(
                    portfolio_id=pid,
                    account_id=aid,
                    event_type="BUY_FILLED",
                    instrument_key=key,
                    trading_date=td,
                    quantity=qty,
                    price=px,
                    cash_delta=-(notional + fee),
                    fee=fee,
                    idempotency_key=idem,
                    message=f"oms buy fill {qty}@{px}",
                    payload={"order_id": order.order_id, "fill_id": fill.fill_id},
                    salt=f"buy|{fill.fill_id}|{i}",
                )
            )
    return events


def bridge_fills_to_portfolio(
    order: Order,
    fills: Sequence[Fill],
    *,
    writer: PortfolioWriter | None = None,
    portfolio_service: Any = None,
    commission_bps: float = _DEFAULT_COMMISSION_BPS,
    stamp_bps: float = _DEFAULT_STAMP_BPS,
) -> list[PositionEvent]:
    """写 PositionEvent；若有 portfolio_service 则尝试 reduce 状态。"""
    events = fills_to_position_events(
        order, fills, commission_bps=commission_bps, stamp_bps=stamp_bps
    )
    if not events:
        return events

    # 优先走 PortfolioService.apply_position_events（若存在）
    if portfolio_service is not None and hasattr(
        portfolio_service, "apply_position_events"
    ):
        portfolio_service.apply_position_events(
            order.portfolio_id, events, account_id=order.account_id
        )
        return events

    if writer is not None:
        for ev in events:
            writer.write_event(ev)
    return events
