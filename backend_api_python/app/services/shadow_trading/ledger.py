"""Phase 7B：Shadow 现金 / 持仓 / 权益 / PnL。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .protocol import ShadowExecution, ShadowPosition


@dataclass
class ShadowLedger:
    """内存账本；成交驱动更新。"""

    cash: float = 100_000.0
    positions: dict[str, ShadowPosition] = field(default_factory=dict)
    realized_pnl: float = 0.0

    def apply_execution(self, execution: ShadowExecution) -> None:
        sym = execution.symbol.upper()
        pos = self.positions.get(sym) or ShadowPosition(symbol=sym, quantity=0.0, avg_price=0.0)
        qty = execution.quantity
        price = execution.price
        fee = execution.fee

        if execution.side == "BUY":
            cost = qty * price + fee
            self.cash -= cost
            new_qty = pos.quantity + qty
            avg = (
                (pos.avg_price * pos.quantity + price * qty) / new_qty
                if new_qty > 1e-12
                else 0.0
            )
            pos = ShadowPosition(symbol=sym, quantity=new_qty, avg_price=avg, market_value=new_qty * price)
        else:
            proceeds = qty * price - fee
            self.cash += proceeds
            new_qty = pos.quantity - qty
            if pos.quantity > 0:
                self.realized_pnl += (price - pos.avg_price) * qty - fee
            pos = ShadowPosition(
                symbol=sym,
                quantity=new_qty,
                avg_price=pos.avg_price if new_qty > 1e-12 else 0.0,
                market_value=max(new_qty, 0.0) * price,
            )
        self.positions[sym] = pos

    def mark_to_market(self, marks: Mapping[str, float]) -> float:
        """按 mark 更新市值并返回 equity。"""
        mv = 0.0
        for sym, pos in self.positions.items():
            px = float(marks.get(sym) or marks.get(sym.upper()) or pos.avg_price or 0.0)
            pos.market_value = pos.quantity * px
            mv += pos.market_value
            self.positions[sym] = pos
        return self.cash + mv

    def equity(self, marks: Mapping[str, float] | None = None) -> float:
        if marks:
            return self.mark_to_market(marks)
        return self.cash + sum(p.market_value for p in self.positions.values())
