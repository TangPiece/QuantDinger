"""截面 RANK / ZSCORE 标准化。"""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, stdev

from .protocol import AlignedRow, CombinationSpec, NormalizedRow


def _average_ranks(values: list[float]) -> list[float]:
    """平均秩（ties）；与 4E 一致。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


class CSNormalizer:
    """按日 × 因子列截面标准化。"""

    def normalize(
        self, rows: list[AlignedRow], spec: CombinationSpec
    ) -> list[NormalizedRow]:
        ids = list(spec.member_factor_dataset_ids)
        by_date: dict = defaultdict(list)
        for r in rows:
            by_date[r.trading_date].append(r)

        out: list[NormalizedRow] = []
        for d in sorted(by_date):
            day = by_date[d]
            # 每列标准化
            col_norm: dict[str, dict[str, float]] = {mid: {} for mid in ids}
            drop_iks: set[str] = set()
            for mid in ids:
                vals = [r.values[mid] for r in day]
                iks = [r.instrument_key for r in day]
                if spec.normalize == "RANK":
                    ranks = _average_ranks(vals)
                    n = len(vals)
                    for ik, rk in zip(iks, ranks):
                        col_norm[mid][ik] = rk / n
                else:  # ZSCORE
                    if len(vals) < 2:
                        drop_iks.update(iks)
                        continue
                    m = mean(vals)
                    s = stdev(vals)
                    if s == 0.0 or math.isnan(s):
                        drop_iks.update(iks)
                        continue
                    for ik, v in zip(iks, vals):
                        col_norm[mid][ik] = (v - m) / s

            for r in day:
                if r.instrument_key in drop_iks:
                    continue
                if any(r.instrument_key not in col_norm[mid] for mid in ids):
                    continue
                out.append(
                    NormalizedRow(
                        trading_date=d,
                        instrument_key=r.instrument_key,
                        values={mid: col_norm[mid][r.instrument_key] for mid in ids},
                    )
                )
        return out
