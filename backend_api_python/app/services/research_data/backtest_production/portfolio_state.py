"""内部组合账本：现金 / 持仓 / 已实现与未实现盈亏 / 累计费用。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from app.services.research_data.backtest.execution.models import MarketBar
from app.services.research_data.backtest.ledger import (
    PortfolioSnapshot,
    PositionSnapshot,
    TradeRecord,
)


@dataclass
class LotPosition:
    """单标的持仓。"""

    quantity: float = 0.0
    average_cost: float = 0.0


@dataclass
class PortfolioState:
    """生产回测运行时账本（非契约类型）。

    数量与现金以 ExecutionSimulator 输出为准（``sync_from_snapshot``）；
    本类额外累计 realized_pnl / total_cost，并做市值估值。
    """

    cash: float
    positions: dict[str, LotPosition] = field(default_factory=dict)
    realized_pnl: float = 0.0
    total_cost: float = 0.0

    def record_fills(self, trades: list[TradeRecord]) -> None:
        """在 sync 之前：按卖出成交累计 realized_pnl 与 total_cost。"""
        for t in trades:
            if t.status not in ("FILLED", "PARTIAL") or t.quantity <= 0:
                continue
            cost = float(t.commission or 0.0) + float(t.tax or 0.0) + float(t.slippage or 0.0)
            self.total_cost += cost
            if t.side != "SELL":
                continue
            pos = self.positions.get(t.instrument_key)
            avg = float(pos.average_cost) if pos else float(t.executed_price or 0.0)
            px = float(t.executed_price or 0.0)
            qty = float(t.quantity)
            self.realized_pnl += (px - avg) * qty - cost

    def sync_from_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        """以 simulator 输出的 PortfolioSnapshot 为权威现金/数量/成本。"""
        self.cash = float(snapshot.cash or 0.0)
        new_pos: dict[str, LotPosition] = {}
        for p in snapshot.positions or []:
            prev = self.positions.get(p.instrument_key)
            avg = float(
                p.average_cost
                if p.average_cost is not None
                else (prev.average_cost if prev else 0.0)
            )
            new_pos[p.instrument_key] = LotPosition(
                quantity=float(p.quantity or 0.0),
                average_cost=avg,
            )
        self.positions = new_pos

    def to_input_snapshot(self, trading_date: str) -> PortfolioSnapshot:
        """构造传入 ExecutionSimulator.step 的输入快照。"""
        positions = [
            PositionSnapshot(
                instrument_key=ik,
                trading_date=trading_date,
                quantity=pos.quantity,
                average_cost=pos.average_cost,
            )
            for ik, pos in self.positions.items()
            if pos.quantity > 1e-12
        ]
        return PortfolioSnapshot(
            trading_date=trading_date,
            cash=float(self.cash),
            total_value=float(self.cash),  # step 前暂不含市值；step 后会重估
            positions=positions,
            realized_pnl=float(self.realized_pnl),
            unrealized_pnl=0.0,
            total_cost=float(self.total_cost),
        )

    def to_snapshot(
        self,
        trading_date: str,
        bars: Mapping[str, MarketBar],
        *,
        price_field: str = "close",
    ) -> PortfolioSnapshot:
        """导出 Domain PortfolioSnapshot（含 realized/unrealized/total_cost）。"""
        positions: list[PositionSnapshot] = []
        mv_total = 0.0
        u_pnl = 0.0
        for ik, pos in self.positions.items():
            bar = bars.get(ik)
            px = None
            if bar is not None:
                px = getattr(bar, price_field, None) or bar.close
            if px is None:
                px = pos.average_cost
            px = float(px or 0.0)
            mv = pos.quantity * px
            up = (px - pos.average_cost) * pos.quantity
            mv_total += mv
            u_pnl += up
            positions.append(
                PositionSnapshot(
                    instrument_key=ik,
                    trading_date=trading_date,
                    quantity=pos.quantity,
                    average_cost=pos.average_cost,
                    market_value=mv,
                    unrealized_pnl=up,
                )
            )
        equity = float(self.cash) + mv_total
        for i, p in enumerate(positions):
            if equity > 0 and p.market_value is not None:
                positions[i] = p.model_copy(
                    update={"weight": float(p.market_value) / equity}
                )
        return PortfolioSnapshot(
            trading_date=trading_date,
            cash=float(self.cash),
            total_value=equity,
            positions=positions,
            realized_pnl=float(self.realized_pnl),
            unrealized_pnl=float(u_pnl),
            total_cost=float(self.total_cost),
        )
