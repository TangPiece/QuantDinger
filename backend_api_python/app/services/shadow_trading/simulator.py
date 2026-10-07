"""Phase 7B：Shadow 成交模拟（Market/Limit + slippage/partial/fee）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from .protocol import ShadowExecution, ShadowOrder


@dataclass
class QuoteLike:
    """模拟用报价（bid/ask）。"""

    bid: float
    ask: float


@dataclass
class SimulatorConfig:
    slippage_bps: float = 5.0
    fee_bps: float = 1.0
    max_fill_qty: Optional[float] = None  # partial 上限


class ShadowExecutionSimulator:
    """根据 quote 对 ShadowOrder 产生 ShadowExecution。"""

    def __init__(self, config: SimulatorConfig | None = None) -> None:
        self._cfg = config or SimulatorConfig()

    def try_fill(
        self,
        order: ShadowOrder,
        quote: QuoteLike,
    ) -> tuple[ShadowOrder, Optional[ShadowExecution]]:
        """返回更新后的 order；无法成交则 execution=None。"""
        remaining = order.quantity - order.filled_quantity
        if remaining <= 0:
            return order, None

        fill_qty = remaining
        if self._cfg.max_fill_qty is not None:
            fill_qty = min(fill_qty, float(self._cfg.max_fill_qty))
        if fill_qty <= 0:
            return order, None

        price = self._price_for_fill(order, quote)
        if price is None:
            return order, None

        notional = price * fill_qty
        fee = notional * (self._cfg.fee_bps / 10000.0)
        exec_id = "sex_" + uuid4().hex[:16]
        execution = ShadowExecution(
            execution_id=exec_id,
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=fill_qty,
            price=price,
            fee=fee,
            slippage_bps=self._cfg.slippage_bps,
            executed_at=datetime.now(timezone.utc).isoformat(),
        )

        new_filled = order.filled_quantity + fill_qty
        status = order.status
        if new_filled >= order.quantity - 1e-9:
            status = "FILLED"
        elif new_filled > 0:
            status = "PARTIALLY_FILLED"

        updated = order.model_copy(
            update={"filled_quantity": new_filled, "status": status}
        )
        return updated, execution

    def _price_for_fill(self, order: ShadowOrder, quote: QuoteLike) -> Optional[float]:
        slip = self._cfg.slippage_bps / 10000.0
        if order.order_type == "MARKET":
            if order.side == "BUY":
                return quote.ask * (1.0 + slip)
            return quote.bid * (1.0 - slip)
        # LIMIT
        lp = order.limit_price
        if lp is None:
            return None
        if order.side == "BUY":
            if quote.ask <= lp:
                return min(lp, quote.ask * (1.0 + slip))
            return None
        if quote.bid >= lp:
            return max(lp, quote.bid * (1.0 - slip))
        return None
