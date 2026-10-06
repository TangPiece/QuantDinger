"""IC / RankIC 时间序列 → FactorEvaluationSummary（ddof=1）。"""

from __future__ import annotations

import math
from statistics import mean, median, stdev
from typing import Optional

from app.services.research_data.contracts import FactorEvaluationSummary

from .protocol import METRIC_VERSION, MetricSpec, MetricTimeSeries


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


def _ir(vals: list[float]) -> Optional[float]:
    """ICIR = mean / sample_std (ddof=1)。"""
    if len(vals) < 2:
        return None
    s = stdev(vals)  # ddof=1
    if s == 0.0:
        return None
    return mean(vals) / s


def _tstat(vals: list[float]) -> Optional[float]:
    """t = mean / (std / sqrt(N))。"""
    n = len(vals)
    if n < 2:
        return None
    s = stdev(vals)
    if s == 0.0:
        return None
    return mean(vals) / (s / math.sqrt(n))


def _pos_ratio(vals: list[float]) -> Optional[float]:
    if not vals:
        return None
    return sum(1 for v in vals if v > 0) / len(vals)


class ICStatisticsAggregator:
    """按 horizon 聚合；不取 abs。"""

    def aggregate(
        self,
        series: MetricTimeSeries,
        spec: MetricSpec,
        *,
        factor_dataset_id: str = "",
    ) -> list[FactorEvaluationSummary]:
        """从 MetricTimeSeries 生成每 horizon 一条 Summary。"""
        out: list[FactorEvaluationSummary] = []
        horizons = series.horizons or sorted({p.horizon for p in series.points})
        for h in horizons:
            day_pts = [p for p in series.points if p.horizon == h]
            total = len(day_pts)
            valid_pts = [p for p in day_pts if p.valid]
            ics = _finite([p.ic for p in valid_pts])
            rics = _finite([p.rank_ic for p in valid_pts])
            out.append(
                FactorEvaluationSummary(
                    metric_hash=series.metric_hash,
                    evaluation_hash=series.evaluation_hash,
                    factor_dataset_id=factor_dataset_id,
                    horizon=int(h),
                    mean_ic=mean(ics) if ics else None,
                    median_ic=median(ics) if ics else None,
                    std_ic=stdev(ics) if len(ics) >= 2 else None,
                    min_ic=min(ics) if ics else None,
                    max_ic=max(ics) if ics else None,
                    ic_ir=_ir(ics),
                    ic_t_stat=_tstat(ics),
                    positive_ic_ratio=_pos_ratio(ics),
                    mean_rank_ic=mean(rics) if rics else None,
                    median_rank_ic=median(rics) if rics else None,
                    std_rank_ic=stdev(rics) if len(rics) >= 2 else None,
                    min_rank_ic=min(rics) if rics else None,
                    max_rank_ic=max(rics) if rics else None,
                    rank_ic_ir=_ir(rics),
                    rank_ic_t_stat=_tstat(rics),
                    positive_rank_ic_ratio=_pos_ratio(rics),
                    valid_day_count=len(valid_pts),
                    total_day_count=total,
                    direction=spec.direction,
                    metric_version=spec.metric_version or METRIC_VERSION,
                )
            )
        return out
