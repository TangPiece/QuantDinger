"""OMS Validation：schema / qty / type / TIF / lot·tick stub（不做风控）。"""

from __future__ import annotations

from typing import Any, Optional

from .protocol import Order


class ValidationError(ValueError):
    """订单校验失败 → REJECTED。"""


_VALID_TYPES = frozenset({"MARKET", "LIMIT"})
_VALID_TIF = frozenset({"DAY", "GTC", "IOC", "FOK"})
_VALID_SIDES = frozenset({"BUY", "SELL"})


def validate_order(
    order: Order,
    *,
    lot_size: float = 1.0,
    tick_size: float = 0.01,
    session_open: bool = True,
) -> Order:
    """轻量校验；失败抛 ValidationError。"""
    if not session_open:
        raise ValidationError("session closed")
    if not order.instrument_key:
        raise ValidationError("instrument_key required")
    if str(order.side) not in _VALID_SIDES:
        raise ValidationError(f"invalid side: {order.side!r}")
    if str(order.order_type) not in _VALID_TYPES:
        raise ValidationError(f"invalid order_type: {order.order_type!r}")
    if str(order.tif) not in _VALID_TIF:
        raise ValidationError(f"invalid tif: {order.tif!r}")
    qty = float(order.quantity)
    if qty <= 0:
        raise ValidationError("quantity must be > 0")
    # lot stub：数量应为 lot_size 整数倍
    if lot_size > 0:
        rem = abs(qty / lot_size - round(qty / lot_size))
        if rem > 1e-9:
            raise ValidationError(f"quantity {qty} not multiple of lot_size {lot_size}")
    if str(order.order_type) == "LIMIT":
        if order.limit_price is None or float(order.limit_price) <= 0:
            raise ValidationError("LIMIT requires positive limit_price")
        # tick stub
        px = float(order.limit_price)
        if tick_size > 0:
            rem = abs(px / tick_size - round(px / tick_size))
            if rem > 1e-9:
                raise ValidationError(
                    f"limit_price {px} not multiple of tick_size {tick_size}"
                )
    if str(order.tif) == "FOK" and str(order.order_type) == "LIMIT":
        # FOK+LIMIT 允许；仅 schema 检查
        pass
    return order


def validate_replace(
    *,
    quantity: Optional[float] = None,
    limit_price: Optional[float] = None,
    lot_size: float = 1.0,
    tick_size: float = 0.01,
) -> None:
    if quantity is not None:
        if float(quantity) <= 0:
            raise ValidationError("replace quantity must be > 0")
        if lot_size > 0:
            rem = abs(float(quantity) / lot_size - round(float(quantity) / lot_size))
            if rem > 1e-9:
                raise ValidationError("replace quantity not multiple of lot_size")
    if limit_price is not None:
        if float(limit_price) <= 0:
            raise ValidationError("replace limit_price must be > 0")
        if tick_size > 0:
            rem = abs(
                float(limit_price) / tick_size - round(float(limit_price) / tick_size)
            )
            if rem > 1e-9:
                raise ValidationError("replace limit_price not multiple of tick_size")


def validation_meta(
    *,
    lot_size: float = 1.0,
    tick_size: float = 0.01,
) -> dict[str, Any]:
    return {"lot_size": lot_size, "tick_size": tick_size}
