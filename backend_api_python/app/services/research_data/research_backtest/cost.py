"""执行成本模型占位；5B 仅 NoCost，5C 再扩展。"""

from __future__ import annotations

from typing import Protocol


class ExecutionCostModel(Protocol):
    """5C 将实现手续费 / 印花税 / 滑点等；5B 仅协议占位。"""

    def cost_for_trade(
        self,
        *,
        notional: float,
        side: str,
    ) -> float:
        """返回绝对成本金额（从 cash 扣除）。"""
        ...


class NoCostModel:
    """零成本模型：commission = slippage = tax = 0。"""

    def cost_for_trade(self, *, notional: float, side: str) -> float:
        return 0.0
