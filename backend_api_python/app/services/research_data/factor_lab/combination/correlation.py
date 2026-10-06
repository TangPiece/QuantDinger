"""相关矩阵 + 冗余对。"""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean
from typing import Optional

from .protocol import (
    CombinationSpec,
    CorrCell,
    NormalizedRow,
    RedundancyPair,
)


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = dx2 = dy2 = 0.0
    for x, y in zip(xs, ys):
        dx = x - mx
        dy = y - my
        num += dx * dy
        dx2 += dx * dx
        dy2 += dy * dy
    if dx2 <= 0.0 or dy2 <= 0.0:
        return None
    return num / math.sqrt(dx2 * dy2)


class CorrelationRedundancyCalculator:
    """日截面相关 → 跨日均值；标记冗余对。"""

    def calculate(
        self, rows: list[NormalizedRow], spec: CombinationSpec
    ) -> tuple[list[CorrCell], list[RedundancyPair], dict]:
        ids = list(spec.member_factor_dataset_ids)
        by_date: dict = defaultdict(list)
        for r in rows:
            by_date[r.trading_date].append(r)

        # pair -> list of daily corrs
        pair_corrs: dict[tuple[str, str], list[float]] = defaultdict(list)
        for _d, day in by_date.items():
            if len(day) < 2:
                continue
            for i, a in enumerate(ids):
                for b in ids[i:]:
                    xs = [r.values[a] for r in day]
                    ys = [r.values[b] for r in day]
                    if a == b:
                        pair_corrs[(a, b)].append(1.0)
                        continue
                    c = _pearson(xs, ys)
                    if c is not None:
                        pair_corrs[(a, b)].append(c)

        cells: list[CorrCell] = []
        matrix: dict[str, dict[str, float]] = {a: {} for a in ids}
        for a in ids:
            for b in ids:
                key = (a, b) if (a, b) in pair_corrs else (b, a)
                vals = pair_corrs.get(key, [])
                c = 1.0 if a == b else (mean(vals) if vals else 0.0)
                matrix[a][b] = c
                cells.append(CorrCell(factor_i=a, factor_j=b, corr=float(c)))

        thr = float(spec.redundancy_corr_threshold)
        pairs: list[RedundancyPair] = []
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                c = matrix[a][b]
                if abs(c) >= thr:
                    pairs.append(RedundancyPair(factor_i=a, factor_j=b, corr=float(c)))

        summary = {
            "matrix": matrix,
            "redundancy_count": len(pairs),
            "threshold": thr,
        }
        return cells, pairs, summary
