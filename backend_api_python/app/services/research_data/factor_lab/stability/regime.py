"""Regime Stability：YEAR / QUARTER 日历分桶（禁止 Bull/Bear 猜测）。"""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean
from typing import Optional

from app.services.research_data.factor_lab.groups.protocol import (
    GroupReturnRow,
    TurnoverRow,
)
from app.services.research_data.factor_lab.metrics.protocol import MetricPoint

from .protocol import RegimeRow, StabilitySpec


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


def _regime_value(d, regime_type: str) -> str:
    """仅由 evaluation_date 导出标签，无未来信息。"""
    if regime_type == "YEAR":
        return f"{d.year:04d}"
    # QUARTER
    q = (d.month - 1) // 3 + 1
    return f"{d.year:04d}-Q{q}"


class RegimeStabilityCalculator:
    """按 YEAR/QUARTER 聚合 IC / LS / turnover / net。"""

    def calculate(
        self,
        points: list[MetricPoint],
        returns: list[GroupReturnRow],
        turnover: list[TurnoverRow],
        spec: StabilitySpec,
    ) -> list[RegimeRow]:
        # LS / net 按 (date, horizon) 去重
        ls_map: dict[tuple, float] = {}
        net_map: dict[tuple, float] = {}
        for r in returns:
            key = (r.evaluation_date, int(r.horizon))
            if key not in ls_map and r.long_short_return is not None:
                try:
                    f = float(r.long_short_return)
                    if not math.isnan(f):
                        ls_map[key] = f
                except (TypeError, ValueError):
                    pass
            if key not in net_map and r.net_long_short_return is not None:
                try:
                    f = float(r.net_long_short_return)
                    if not math.isnan(f):
                        net_map[key] = f
                except (TypeError, ValueError):
                    pass

        turn_map: dict[tuple, float] = {}
        for t in turnover:
            if t.portfolio != "LONG_SHORT":
                continue
            key = (t.evaluation_date, int(t.horizon))
            if t.turnover is None:
                continue
            try:
                f = float(t.turnover)
                if not math.isnan(f):
                    turn_map[key] = f
            except (TypeError, ValueError):
                pass

        # bucket: (regime_type, value, horizon) -> lists
        buckets: dict[tuple, dict[str, list]] = defaultdict(
            lambda: {
                "ic": [],
                "rank_ic": [],
                "ls": [],
                "turn": [],
                "net": [],
            }
        )
        for p in points:
            if not p.valid:
                continue
            h = int(p.horizon)
            for rt in spec.regime_types:
                rv = _regime_value(p.evaluation_date, rt)
                b = buckets[(rt, rv, h)]
                if p.ic is not None:
                    try:
                        f = float(p.ic)
                        if not math.isnan(f):
                            b["ic"].append(f)
                    except (TypeError, ValueError):
                        pass
                if p.rank_ic is not None:
                    try:
                        f = float(p.rank_ic)
                        if not math.isnan(f):
                            b["rank_ic"].append(f)
                    except (TypeError, ValueError):
                        pass
                key = (p.evaluation_date, h)
                if key in ls_map:
                    b["ls"].append(ls_map[key])
                if key in turn_map:
                    b["turn"].append(turn_map[key])
                if key in net_map:
                    b["net"].append(net_map[key])

        out: list[RegimeRow] = []
        for (rt, rv, h), b in sorted(buckets.items()):
            ics = _finite(b["ic"])
            rics = _finite(b["rank_ic"])
            lss = _finite(b["ls"])
            turns = _finite(b["turn"])
            nets = _finite(b["net"])
            out.append(
                RegimeRow(
                    regime_type=rt,  # type: ignore[arg-type]
                    regime_value=rv,
                    horizon=h,
                    ic_mean=mean(ics) if ics else None,
                    rankic_mean=mean(rics) if rics else None,
                    long_short_return=mean(lss) if lss else None,
                    turnover=mean(turns) if turns else None,
                    net_return=mean(nets) if nets else None,
                    sample_count=max(len(ics), len(lss)),
                )
            )
        return out
