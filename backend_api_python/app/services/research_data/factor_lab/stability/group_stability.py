"""Group Stability：消费同次 run 的 GroupReturnRow，不重做分位。"""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, stdev
from typing import Literal, Optional

from app.services.research_data.factor_lab.groups.protocol import GroupReturnRow

from .protocol import GroupStabilityRow, StabilitySpec


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


class GroupStabilityCalculator:
    """Top/Bottom/LONG/SHORT/LS 的 trailing mean/std/pos_ratio。"""

    def calculate(
        self,
        returns: list[GroupReturnRow],
        spec: StabilitySpec,
        *,
        direction: Literal["POSITIVE", "NEGATIVE"],
        long_group: int,
        short_group: int,
    ) -> list[GroupStabilityRow]:
        """按 horizon × portfolio 构建日序列，再算各 rolling window。

        ``direction`` 由调用方已解析；此处用 long/short group 定位 Top/Bottom。
        """
        _ = direction  # 与 4E 调用约定对齐，分组结果已按 direction 写好 LS
        # date -> horizon -> series values
        series: dict[tuple, dict[str, float]] = {}
        for r in returns:
            key = (r.evaluation_date, int(r.horizon))
            bucket = series.setdefault(key, {})
            # group 收益：Top/Bottom
            if int(r.group) == int(long_group) and r.group_return is not None:
                bucket["TOP"] = float(r.group_return)
                bucket["LONG"] = (
                    float(r.long_return)
                    if r.long_return is not None
                    else float(r.group_return)
                )
            if int(r.group) == int(short_group) and r.group_return is not None:
                bucket["BOTTOM"] = float(r.group_return)
                if r.short_return is not None:
                    bucket["SHORT"] = float(r.short_return)
            if r.long_short_return is not None:
                bucket["LONG_SHORT"] = float(r.long_short_return)

        by_h_port: dict[tuple[int, str], list[tuple]] = defaultdict(list)
        for (d, h), vals in sorted(series.items(), key=lambda x: (x[0][1], x[0][0])):
            for port, val in vals.items():
                by_h_port[(h, port)].append((d, val))

        out: list[GroupStabilityRow] = []
        min_n = int(spec.min_rolling_samples)
        for (h, port), seq in sorted(by_h_port.items()):
            for i, (d, _) in enumerate(seq):
                for w in spec.rolling_windows:
                    start = max(0, i - int(w) + 1)
                    window_vals = _finite([v for _, v in seq[start : i + 1]])
                    n = len(window_vals)
                    if n < min_n:
                        out.append(
                            GroupStabilityRow(
                                evaluation_date=d,
                                horizon=h,
                                window=int(w),
                                portfolio=port,
                                mean_return=None,
                                std_return=None,
                                positive_ratio=None,
                                sample_count=n,
                            )
                        )
                        continue
                    out.append(
                        GroupStabilityRow(
                            evaluation_date=d,
                            horizon=h,
                            window=int(w),
                            portfolio=port,
                            mean_return=mean(window_vals),
                            std_return=stdev(window_vals) if n >= 2 else None,
                            positive_ratio=sum(1 for v in window_vals if v > 0) / n,
                            sample_count=n,
                        )
                    )
        return out
