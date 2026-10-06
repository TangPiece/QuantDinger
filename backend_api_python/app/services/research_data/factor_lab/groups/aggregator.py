"""GroupFrames → GroupEvaluationSummary。"""

from __future__ import annotations

import math
from statistics import mean
from typing import Literal, Optional, Sequence

from app.services.research_data.contracts import GroupEvaluationSummary

from .protocol import GROUP_VERSION, GroupFrames, GroupReturnRow, GroupSpec, TurnoverRow


def _finite(vals: Sequence[Optional[float]]) -> list[float]:
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


class GroupEvaluationAggregator:
    """按 horizon 聚合；不计算 CAGR/Sharpe。"""

    def aggregate(
        self,
        frames: GroupFrames,
        spec: GroupSpec,
        *,
        direction: Literal["POSITIVE", "NEGATIVE"],
        factor_dataset_id: str = "",
    ) -> list[GroupEvaluationSummary]:
        n_g = int(spec.group_count)
        long_g = 1 if direction == "POSITIVE" else n_g
        short_g = n_g if direction == "POSITIVE" else 1
        out: list[GroupEvaluationSummary] = []

        for h in frames.horizons:
            # 每个交易日取 group=long_g 那一行上的 LS 字段（各 group 行重复）
            day_rows = [
                r
                for r in frames.returns
                if r.horizon == h and r.group == long_g
            ]
            total = len({r.evaluation_date for r in frames.returns if r.horizon == h})
            longs = _finite([r.long_return for r in day_rows])
            shorts = _finite([r.short_return for r in day_rows])
            lss = _finite([r.long_short_return for r in day_rows])
            nets = _finite([r.net_long_short_return for r in day_rows])
            costs = _finite([r.estimated_cost for r in day_rows])
            turns = _finite(
                [
                    t.turnover
                    for t in frames.turnover
                    if t.horizon == h and t.portfolio == "LONG_SHORT"
                ]
            )
            out.append(
                GroupEvaluationSummary(
                    group_evaluation_hash=frames.group_evaluation_hash,
                    evaluation_hash=frames.evaluation_hash,
                    factor_dataset_id=factor_dataset_id,
                    horizon=int(h),
                    group_count=n_g,
                    weighting_method=spec.weighting_method,
                    direction=direction,
                    portfolio_mode=spec.portfolio_mode,
                    long_group=long_g,
                    short_group=short_g,
                    mean_long_return=mean(longs) if longs else None,
                    mean_short_return=mean(shorts) if shorts else None,
                    mean_long_short_return=mean(lss) if lss else None,
                    mean_turnover=mean(turns) if turns else None,
                    mean_estimated_cost=mean(costs) if costs else None,
                    mean_net_long_short_return=mean(nets) if nets else None,
                    valid_day_count=len(lss),
                    total_day_count=total,
                    group_version=spec.group_version or GROUP_VERSION,
                )
            )
        return out
