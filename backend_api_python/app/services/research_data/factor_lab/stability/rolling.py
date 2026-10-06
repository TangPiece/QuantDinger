"""Rolling IC / RankIC：严格 trailing 窗口，禁止 look-ahead。"""

from __future__ import annotations

import math
from statistics import mean, stdev
from typing import Optional

from app.services.research_data.factor_lab.metrics.protocol import MetricPoint

from .protocol import RollingICRow, StabilitySpec


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


class RollingICCalculator:
    """对每个 (horizon, window, date T) 只用 evaluation_date <= T 的 trailing 观测。"""

    def calculate(
        self,
        points: list[MetricPoint],
        spec: StabilitySpec,
    ) -> list[RollingICRow]:
        """生成滚动 IC 行；窗口内有效样本不足则指标为 null。"""
        by_h: dict[int, list[MetricPoint]] = {}
        for p in points:
            by_h.setdefault(int(p.horizon), []).append(p)
        out: list[RollingICRow] = []
        min_n = int(spec.min_rolling_samples)
        for h, pts in sorted(by_h.items()):
            # 按日期升序；同日取最后一条
            ordered = sorted(pts, key=lambda x: x.evaluation_date)
            for i, cur in enumerate(ordered):
                for w in spec.rolling_windows:
                    # trailing：序列位置 [i-w+1, i]，含 T
                    start = max(0, i - int(w) + 1)
                    window_pts = ordered[start : i + 1]
                    ics = _finite(
                        [p.ic for p in window_pts if p.valid]
                    )
                    rics = _finite(
                        [p.rank_ic for p in window_pts if p.valid]
                    )
                    n = len(ics)
                    if n < min_n:
                        out.append(
                            RollingICRow(
                                evaluation_date=cur.evaluation_date,
                                horizon=h,
                                window=int(w),
                                ic_mean=None,
                                rankic_mean=None,
                                ic_std=None,
                                ic_positive_ratio=None,
                                sample_count=n,
                            )
                        )
                        continue
                    out.append(
                        RollingICRow(
                            evaluation_date=cur.evaluation_date,
                            horizon=h,
                            window=int(w),
                            ic_mean=mean(ics),
                            rankic_mean=mean(rics) if rics else None,
                            ic_std=stdev(ics) if n >= 2 else None,
                            ic_positive_ratio=sum(1 for v in ics if v > 0) / n,
                            sample_count=n,
                        )
                    )
        return out
