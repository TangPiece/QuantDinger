"""Turnover = 0.5 * Σ|w_t - w_{t-1}|；首日 NaN。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Literal, Sequence

from .protocol import GroupSpec, MembershipRow, TurnoverRow


class TurnoverCalculator:
    """按 portfolio（GROUP_k / LONG / SHORT / LONG_SHORT）计算换手。"""

    def calculate(
        self,
        membership: Sequence[MembershipRow],
        spec: GroupSpec,
        *,
        direction: Literal["POSITIVE", "NEGATIVE"],
    ) -> list[TurnoverRow]:
        n_g = int(spec.group_count)
        long_g = 1 if direction == "POSITIVE" else n_g
        short_g = n_g if direction == "POSITIVE" else 1

        # weights[(date, horizon, portfolio)][instrument] = weight
        # LONG: +w in long group; SHORT: +w in short; LONG_SHORT: long +w, short -w
        by_day_h: dict[tuple[date, int], list[MembershipRow]] = defaultdict(list)
        for m in membership:
            by_day_h[(m.evaluation_date, m.horizon)].append(m)

        horizons = sorted({m.horizon for m in membership})
        out: list[TurnoverRow] = []

        for h in horizons:
            days = sorted(d for (d, hh) in by_day_h if hh == h)
            prev: dict[str, dict[str, float]] = {}
            for i, d in enumerate(days):
                members = by_day_h[(d, h)]
                portfolios = self._portfolios(members, n_g, long_g, short_g)
                for pname, weights in portfolios.items():
                    if i == 0:
                        turn = None  # 首日 NaN
                        prev_n = 0
                    else:
                        prev_w = prev.get(pname, {})
                        turn = self._turnover(prev_w, weights)
                        prev_n = len(prev_w)
                    out.append(
                        TurnoverRow(
                            evaluation_date=d,
                            horizon=h,
                            portfolio=pname,
                            turnover=turn,
                            previous_weight_count=prev_n,
                            current_weight_count=len(weights),
                        )
                    )
                    prev[pname] = weights
        return out

    def _portfolios(
        self,
        members: Sequence[MembershipRow],
        n_g: int,
        long_g: int,
        short_g: int,
    ) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for g in range(1, n_g + 1):
            w = {m.instrument_key: m.weight for m in members if m.group == g}
            out[f"GROUP_{g}"] = w
        long_w = {m.instrument_key: m.weight for m in members if m.group == long_g}
        short_w = {m.instrument_key: m.weight for m in members if m.group == short_g}
        out["LONG"] = long_w
        out["SHORT"] = short_w
        # LONG_SHORT：多头 +w，空头 -w（换手按绝对值变化）
        ls: dict[str, float] = {}
        for k, v in long_w.items():
            ls[k] = ls.get(k, 0.0) + v
        for k, v in short_w.items():
            ls[k] = ls.get(k, 0.0) - v
        out["LONG_SHORT"] = ls
        return out

    @staticmethod
    def _turnover(prev: dict[str, float], cur: dict[str, float]) -> float:
        keys = set(prev) | set(cur)
        return 0.5 * sum(abs(cur.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
