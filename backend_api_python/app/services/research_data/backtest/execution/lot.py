"""整手 / tick 舍入（按 TradingRule.lot_rounding Contract）。"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.research_data.backtest.policy import TradingRule

from .models import REASON_LOT_SIZE_FLOOR, REASON_LOT_SIZE_REJECT, REASON_OK


@dataclass(frozen=True)
class LotAdjustResult:
    """整手调整结果。"""

    executable_quantity: float
    rejected_quantity: float
    reason: str


def adjust_lot_quantity(quantity: float, rule: TradingRule) -> LotAdjustResult:
    """按 lot_rounding 调整下单数量。

    - fractional_shares 或 lot_size<=1：原样通过
    - floor：向下取整到 lot_size 倍数；零头 → rejected，reason=LOT_SIZE_FLOOR
    - reject：非整手整单拒绝，reason=LOT_SIZE_REJECT
    """
    qty = abs(float(quantity))
    if qty <= 0:
        return LotAdjustResult(0.0, 0.0, REASON_OK)

    if rule.fractional_shares or int(rule.lot_size or 1) <= 1:
        return LotAdjustResult(qty, 0.0, REASON_OK)

    lot = int(rule.lot_size)
    # 用整数股判断整手（数量按股计）
    qty_shares = int(round(qty))
    if abs(qty - qty_shares) > 1e-9:
        qty_shares = int(qty)

    if rule.lot_rounding == "reject":
        if qty_shares % lot != 0:
            return LotAdjustResult(0.0, qty, REASON_LOT_SIZE_REJECT)
        return LotAdjustResult(float(qty_shares), 0.0, REASON_OK)

    # floor（默认）
    rounded = (qty_shares // lot) * lot
    remainder = float(qty_shares - rounded)
    if rounded <= 0:
        return LotAdjustResult(0.0, qty, REASON_LOT_SIZE_FLOOR)
    if remainder > 0:
        return LotAdjustResult(float(rounded), remainder, REASON_LOT_SIZE_FLOOR)
    return LotAdjustResult(float(rounded), 0.0, REASON_OK)


def round_price_to_tick(price: float, tick_size: float) -> float:
    """价格按 tick 向下对齐（研究简化）。"""
    if tick_size is None or tick_size <= 0:
        return float(price)
    ticks = int(float(price) / tick_size + 1e-12)
    return round(ticks * tick_size, 10)
