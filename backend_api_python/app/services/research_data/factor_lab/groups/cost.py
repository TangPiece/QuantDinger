"""Evaluation Cost Model：ZERO / FIXED_BPS（非撮合）。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Optional, Sequence

from .protocol import CostModelSpec, GroupReturnRow, TurnoverRow


class CostCalculator:
    """将 LONG_SHORT turnover 映射为 estimated_cost / net_return。"""

    def apply(
        self,
        returns: Sequence[GroupReturnRow],
        turnover: Sequence[TurnoverRow],
        cost: CostModelSpec,
    ) -> list[GroupReturnRow]:
        """按 (date, horizon) 用 LONG_SHORT turnover 估算成本并写回 return 行。"""
        ls_turn: dict[tuple[date, int], Optional[float]] = {}
        for t in turnover:
            if t.portfolio == "LONG_SHORT":
                ls_turn[(t.evaluation_date, t.horizon)] = t.turnover

        out: list[GroupReturnRow] = []
        for r in returns:
            turn = ls_turn.get((r.evaluation_date, r.horizon))
            est = self._estimate(turn, cost)
            net = None
            if r.long_short_return is not None and est is not None:
                net = float(r.long_short_return) - float(est)
            elif r.long_short_return is not None and cost.kind == "ZERO":
                net = float(r.long_short_return)
                est = 0.0
            out.append(
                r.model_copy(
                    update={
                        "estimated_cost": est,
                        "net_long_short_return": net,
                    }
                )
            )
        return out

    def _estimate(
        self, turnover: Optional[float], cost: CostModelSpec
    ) -> Optional[float]:
        if turnover is None:
            return None
        if cost.kind == "ZERO":
            return 0.0
        # FIXED_BPS：买卖成本均值 × 换手（评价估算）
        avg_bps = (float(cost.buy_cost_bps) + float(cost.sell_cost_bps)) / 2.0
        return float(turnover) * (avg_bps / 10000.0)
