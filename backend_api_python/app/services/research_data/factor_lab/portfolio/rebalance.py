"""调仓日历 + min_turnover hold-forward。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Optional

from .protocol import PortfolioPositionRow, PortfolioSpec, PortfolioTurnoverRow


def _turnover(
    prev: dict[str, float], curr: dict[str, float]
) -> float:
    """0.5 * Σ|Δw|。"""
    keys = set(prev) | set(curr)
    return 0.5 * sum(abs(curr.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)


def _to_map(rows: list[PortfolioPositionRow]) -> dict[str, float]:
    m: dict[str, float] = defaultdict(float)
    for r in rows:
        m[r.instrument_key] += float(r.weight)
    return dict(m)


def _from_map(
    wmap: dict[str, float],
    *,
    trading_date: date,
    template: list[PortfolioPositionRow] | None,
) -> list[PortfolioPositionRow]:
    """按权重图还原行；优先保留 template 的 leg/factor_value。"""
    meta: dict[str, PortfolioPositionRow] = {}
    if template:
        for r in template:
            meta[r.instrument_key] = r
    out: list[PortfolioPositionRow] = []
    for ik, w in sorted(wmap.items()):
        if abs(w) < 1e-15:
            continue
        t = meta.get(ik)
        out.append(
            PortfolioPositionRow(
                trading_date=trading_date,
                instrument_key=ik,
                weight=float(w),
                leg=(t.leg if t else ("LONG" if w >= 0 else "SHORT")),
                factor_value=(t.factor_value if t else None),
            )
        )
    return out


def pick_rebalance_dates(
    all_dates: list[date], frequency: str
) -> set[date]:
    """从有因子的日期中挑选调仓日。"""
    if not all_dates:
        return set()
    if frequency == "DAILY":
        return set(all_dates)
    chosen: list[date] = []
    seen: set = set()
    for d in sorted(all_dates):
        if frequency == "WEEKLY":
            key = (d.isocalendar()[0], d.isocalendar()[1])
        else:  # MONTHLY
            key = (d.year, d.month)
        if key in seen:
            continue
        seen.add(key)
        chosen.append(d)
    return set(chosen)


class RebalanceEngine:
    """候选目标 → 生效持仓轨迹 + 换手。"""

    def apply(
        self,
        candidates: dict[date, list[PortfolioPositionRow]],
        spec: PortfolioSpec,
    ) -> tuple[list[PortfolioPositionRow], list[PortfolioTurnoverRow]]:
        dates = sorted(candidates.keys())
        if not dates:
            return [], []
        rebal_days = pick_rebalance_dates(dates, spec.rebalance_frequency)
        min_to = float(spec.min_turnover)

        effective: dict[date, list[PortfolioPositionRow]] = {}
        prev_map: Optional[dict[str, float]] = None
        turnover_rows: list[PortfolioTurnoverRow] = []

        for d in dates:
            cand = candidates[d]
            cand_map = _to_map(cand)
            is_rebal_day = d in rebal_days

            if prev_map is None:
                # 首日强制生效
                effective[d] = [
                    r.model_copy(update={"trading_date": d}) for r in cand
                ]
                prev_map = cand_map
                turnover_rows.append(
                    PortfolioTurnoverRow(
                        trading_date=d, turnover=None, rebalanced=True
                    )
                )
                continue

            if not is_rebal_day:
                # hold-forward
                effective[d] = _from_map(
                    prev_map, trading_date=d, template=effective.get(dates[dates.index(d) - 1])
                )
                turnover_rows.append(
                    PortfolioTurnoverRow(
                        trading_date=d, turnover=0.0, rebalanced=False
                    )
                )
                continue

            to = _turnover(prev_map, cand_map)
            if to < min_to:
                # 跳过调仓
                effective[d] = _from_map(
                    prev_map,
                    trading_date=d,
                    template=effective.get(dates[dates.index(d) - 1]),
                )
                turnover_rows.append(
                    PortfolioTurnoverRow(
                        trading_date=d, turnover=to, rebalanced=False
                    )
                )
            else:
                effective[d] = [
                    r.model_copy(update={"trading_date": d}) for r in cand
                ]
                prev_map = cand_map
                turnover_rows.append(
                    PortfolioTurnoverRow(
                        trading_date=d, turnover=to, rebalanced=True
                    )
                )

        # 展平
        flat: list[PortfolioPositionRow] = []
        for d in dates:
            flat.extend(effective[d])
        return flat, turnover_rows
