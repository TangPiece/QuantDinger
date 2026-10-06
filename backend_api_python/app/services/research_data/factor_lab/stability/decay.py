"""Decay：各 horizon 的 IC / RankIC / Long-Short 观测（无拟合）。"""

from __future__ import annotations

import math
from statistics import mean
from typing import Optional

from app.services.research_data.factor_lab.groups.protocol import GroupReturnRow
from app.services.research_data.factor_lab.metrics.protocol import MetricPoint

from .protocol import DecayPoint


def _finite(vals: list[Optional[float]]) -> list[float]:
    out: list[float] = []
    for v in vals:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isnan(f) or math.isinf(f):
            continue
        out.append(f)
    return out


class DecayCalculator:
    """按 horizon 聚合全日均值；LS 来自同次 run 的 GroupReturnRow。"""

    def calculate(
        self,
        points: list[MetricPoint],
        returns: list[GroupReturnRow],
        horizons: list[int],
    ) -> list[DecayPoint]:
        out: list[DecayPoint] = []
        for h in horizons:
            valid = [p for p in points if int(p.horizon) == h and p.valid]
            ics = _finite([p.ic for p in valid])
            rics = _finite([p.rank_ic for p in valid])
            # 每个 (date,h) 的 LS 在各 group 行上重复；按日期去重取一次
            seen_dates: set = set()
            longs: list[float] = []
            shorts: list[float] = []
            lss: list[float] = []
            for r in returns:
                if int(r.horizon) != h:
                    continue
                key = (r.evaluation_date, h)
                if key in seen_dates:
                    continue
                seen_dates.add(key)
                if r.long_return is not None and not math.isnan(
                    float(r.long_return)
                ):
                    longs.append(float(r.long_return))
                if r.short_return is not None and not math.isnan(
                    float(r.short_return)
                ):
                    shorts.append(float(r.short_return))
                if r.long_short_return is not None and not math.isnan(
                    float(r.long_short_return)
                ):
                    lss.append(float(r.long_short_return))
            out.append(
                DecayPoint(
                    horizon=int(h),
                    ic_mean=mean(ics) if ics else None,
                    rankic_mean=mean(rics) if rics else None,
                    long_return=mean(longs) if longs else None,
                    short_return=mean(shorts) if shorts else None,
                    long_short_return=mean(lss) if lss else None,
                    sample_count=max(len(ics), len(lss)),
                )
            )
        return out
