"""IC / RankIC 全样本分布统计。"""

from __future__ import annotations

import math
from statistics import mean, median, stdev
from typing import Optional

import numpy as np

from app.services.research_data.factor_lab.metrics.protocol import MetricPoint

from .protocol import ICDistribution


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


def _pct(vals: list[float], q: float) -> Optional[float]:
    if not vals:
        return None
    return float(np.percentile(vals, q))


class ICDistributionCalculator:
    """按 horizon 计算 IC / RankIC 分布；ddof=1。"""

    def calculate(self, points: list[MetricPoint]) -> list[ICDistribution]:
        horizons = sorted({int(p.horizon) for p in points})
        out: list[ICDistribution] = []
        for h in horizons:
            valid = [p for p in points if int(p.horizon) == h and p.valid]
            ics = _finite([p.ic for p in valid])
            rics = _finite([p.rank_ic for p in valid])
            out.append(self._one("IC", h, ics))
            out.append(self._one("RANK_IC", h, rics))
        return out

    def _one(
        self, metric: str, horizon: int, vals: list[float]
    ) -> ICDistribution:
        n = len(vals)
        if n == 0:
            return ICDistribution(
                metric=metric,  # type: ignore[arg-type]
                horizon=horizon,
                sample_count=0,
            )
        return ICDistribution(
            metric=metric,  # type: ignore[arg-type]
            horizon=horizon,
            mean=mean(vals),
            median=median(vals),
            std=stdev(vals) if n >= 2 else None,
            min=min(vals),
            max=max(vals),
            p05=_pct(vals, 5),
            p25=_pct(vals, 25),
            p50=_pct(vals, 50),
            p75=_pct(vals, 75),
            p95=_pct(vals, 95),
            positive_ratio=sum(1 for v in vals if v > 0) / n,
            negative_ratio=sum(1 for v in vals if v < 0) / n,
            sample_count=n,
        )
