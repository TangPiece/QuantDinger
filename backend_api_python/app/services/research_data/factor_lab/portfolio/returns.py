"""理论组合日收益（gross，无成本）。"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Optional

from .protocol import (
    PortfolioPositionRow,
    PortfolioReturnRow,
    PortfolioSpec,
)


def _as_date(v: Any) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if hasattr(v, "date") and not isinstance(v, date):
        return v.date()
    return date.fromisoformat(str(v)[:10])


def _is_nan(v: Any) -> bool:
    if v is None:
        return True
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return True


class PortfolioReturnCalculator:
    """r_t = Σ w_i * forward_return；缺失票剔除后重标定。"""

    def calculate(
        self,
        positions: list[PortfolioPositionRow],
        evaluation_records: list[dict[str, Any]],
        spec: PortfolioSpec,
    ) -> list[PortfolioReturnRow]:
        h = int(spec.horizon)
        col = f"forward_return_{h}d"
        ret_map: dict[tuple[date, str], float] = {}
        for r in evaluation_records:
            if _is_nan(r.get(col)):
                continue
            d = _as_date(r.get("factor_date") or r.get("evaluation_date") or r.get("trading_date"))
            ik = str(r["instrument_key"])
            ret_map[(d, ik)] = float(r[col])

        by_date: dict[date, list[PortfolioPositionRow]] = defaultdict(list)
        for p in positions:
            by_date[p.trading_date].append(p)

        out: list[PortfolioReturnRow] = []
        for d in sorted(by_date):
            day = by_date[d]
            if spec.construction_method == "QUANTILE":
                row = self._quantile_day(day, ret_map, d, spec)
            else:
                row = self._book_day(day, ret_map, d)
            out.append(row)
        return out

    def _weighted(
        self,
        rows: list[PortfolioPositionRow],
        ret_map: dict[tuple[date, str], float],
        d: date,
    ) -> tuple[Optional[float], int]:
        contrib = []
        weights = []
        for p in rows:
            rv = ret_map.get((d, p.instrument_key))
            if rv is None:
                continue
            contrib.append(float(p.weight) * rv)
            weights.append(float(p.weight))
        if not contrib:
            return None, 0
        wsum = sum(weights)
        if abs(wsum) < 1e-15:
            return None, 0
        # 按剩余权重重标定（保持原方向和）
        scale = sum(weights)  # 用有效权重和归一到「有效子集」相对贡献
        # r = Σ (w_i / Σ|有效 w|) * r_i * sign_target；更简单：Σ w_i*r_i / Σ w_i * target_sum
        # 计划：剔除后重标定 → 有效权重归一到原 sum(weights of all intended for that side)
        target = sum(float(p.weight) for p in rows)
        r = sum(contrib) / wsum * target
        return float(r), len(contrib)

    def _book_day(
        self,
        day: list[PortfolioPositionRow],
        ret_map: dict[tuple[date, str], float],
        d: date,
    ) -> PortfolioReturnRow:
        longs = [p for p in day if p.leg == "LONG" or p.weight > 0]
        shorts = [p for p in day if p.leg == "SHORT" or p.weight < 0]
        # LONG_ONLY：全部为正
        if not shorts and all(p.weight >= 0 for p in day):
            pr, n = self._weighted(day, ret_map, d)
            return PortfolioReturnRow(
                trading_date=d,
                portfolio_return=pr,
                long_return=pr,
                short_return=None,
                long_short_return=pr,
                sample_count=n,
            )
        lr, nl = self._weighted(longs, ret_map, d) if longs else (None, 0)
        sr, ns = self._weighted(shorts, ret_map, d) if shorts else (None, 0)
        ls = None
        if lr is not None and sr is not None:
            ls = lr + sr  # short 权重已为负，sr 已是负权重×收益
        elif lr is not None:
            ls = lr
        pr = ls
        return PortfolioReturnRow(
            trading_date=d,
            portfolio_return=pr,
            long_return=lr,
            short_return=sr,
            long_short_return=ls,
            sample_count=nl + ns,
        )

    def _quantile_day(
        self,
        day: list[PortfolioPositionRow],
        ret_map: dict[tuple[date, str], float],
        d: date,
        spec: PortfolioSpec,
    ) -> PortfolioReturnRow:
        n_g = int(spec.group_count)
        by_leg: dict[str, list[PortfolioPositionRow]] = defaultdict(list)
        for p in day:
            by_leg[p.leg].append(p)
        q1 = by_leg.get("Q1", [])
        qn = by_leg.get(f"Q{n_g}", [])
        r1, n1 = self._weighted(q1, ret_map, d) if q1 else (None, 0)
        rn, nn = self._weighted(qn, ret_map, d) if qn else (None, 0)
        ls = None
        if r1 is not None and rn is not None:
            ls = r1 - rn
        return PortfolioReturnRow(
            trading_date=d,
            portfolio_return=ls,
            long_return=r1,
            short_return=rn,
            long_short_return=ls,
            sample_count=n1 + nn,
        )
