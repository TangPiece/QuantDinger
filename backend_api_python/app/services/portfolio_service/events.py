"""PositionEvent 构造辅助。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .hash import compute_event_id
from .protocol import PositionEvent, PositionEventType


def make_event(
    *,
    portfolio_id: str,
    account_id: str,
    event_type: PositionEventType | str,
    instrument_key: str = "",
    trading_date: str = "",
    quantity: float = 0.0,
    price: float = 0.0,
    cash_delta: float = 0.0,
    fee: float = 0.0,
    idempotency_key: str = "",
    message: str = "",
    payload: dict[str, Any] | None = None,
    salt: str = "",
) -> PositionEvent:
    """构造一条 PositionEvent。"""
    now = datetime.now(timezone.utc).isoformat()
    return PositionEvent(
        event_id=compute_event_id(
            portfolio_id=portfolio_id,
            event_type=str(event_type),
            instrument_key=instrument_key,
            salt=salt or f"{trading_date}|{quantity}|{price}|{now}",
        ),
        portfolio_id=portfolio_id,
        account_id=account_id,
        event_type=event_type,
        instrument_key=instrument_key,
        trading_date=trading_date,
        quantity=float(quantity),
        price=float(price),
        cash_delta=float(cash_delta),
        fee=float(fee),
        idempotency_key=idempotency_key,
        message=message,
        payload=dict(payload or {}),
        created_at=now,
    )
