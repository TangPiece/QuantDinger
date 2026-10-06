"""截面选股：LongOnly / LongShort / Quantile。"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from .protocol import PortfolioPositionRow, PortfolioSpec
from .weighting import allocate_weights


def _as_date(v: Any) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if hasattr(v, "date") and not isinstance(v, date):
        return v.date()
    return date.fromisoformat(str(v)[:10])


def _average_ranks(values: list[float]) -> list[float]:
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


def _group_from_rank(rank: float, n: int, n_g: int) -> int:
    """因子越高 rank 越大 → G1。"""
    pct = rank / n
    bucket_low_first = min(n_g, max(1, math.ceil(pct * n_g)))
    return int(n_g + 1 - bucket_low_first)


class PortfolioSelector:
    """按日截面选股并分配目标权重（调仓日候选；尚未 hold-forward）。"""

    def select_day(
        self,
        day_rows: list[dict[str, Any]],
        spec: PortfolioSpec,
        *,
        trading_date: date,
    ) -> list[PortfolioPositionRow]:
        """单日选股；day_rows 含 instrument_key + factor_value。"""
        if len(day_rows) < int(spec.min_cross_section_size):
            return []

        items = []
        for r in day_rows:
            fv = r.get("factor_value", r.get("value"))
            if fv is None:
                continue
            try:
                score = float(fv)
            except (TypeError, ValueError):
                continue
            # NEGATIVE：翻转高低端
            if spec.direction == "NEGATIVE":
                score = -score
            items.append(
                {
                    "instrument_key": str(r["instrument_key"]),
                    "factor_value": float(fv),
                    "score": score,
                }
            )
        n = len(items)
        if n < int(spec.min_cross_section_size):
            return []

        if spec.construction_method == "QUANTILE":
            return self._quantile(items, spec, trading_date=trading_date)

        # 按 score 降序
        items.sort(key=lambda x: (-x["score"], x["instrument_key"]))
        k = self._selection_size(n, spec)
        if k < 1:
            return []

        if spec.construction_method == "LONG_ONLY":
            chosen = items[:k]
            ws = allocate_weights(
                [c["score"] for c in chosen],
                method=spec.weight_method,
                sign=1.0,
            )
            return [
                PortfolioPositionRow(
                    trading_date=trading_date,
                    instrument_key=c["instrument_key"],
                    weight=float(w),
                    leg="LONG",
                    factor_value=c["factor_value"],
                )
                for c, w in zip(chosen, ws)
            ]

        # LONG_SHORT
        longs = items[:k]
        shorts = list(reversed(items[-k:]))
        # 避免重叠（小样本）
        long_keys = {c["instrument_key"] for c in longs}
        shorts = [c for c in shorts if c["instrument_key"] not in long_keys]
        if not longs or not shorts:
            return []
        lw = allocate_weights(
            [c["score"] for c in longs], method=spec.weight_method, sign=1.0
        )
        sw = allocate_weights(
            [c["score"] for c in shorts], method=spec.weight_method, sign=-1.0
        )
        out = [
            PortfolioPositionRow(
                trading_date=trading_date,
                instrument_key=c["instrument_key"],
                weight=float(w),
                leg="LONG",
                factor_value=c["factor_value"],
            )
            for c, w in zip(longs, lw)
        ]
        out += [
            PortfolioPositionRow(
                trading_date=trading_date,
                instrument_key=c["instrument_key"],
                weight=float(w),
                leg="SHORT",
                factor_value=c["factor_value"],
            )
            for c, w in zip(shorts, sw)
        ]
        return out

    def select_all(
        self, factor_rows: list[dict[str, Any]], spec: PortfolioSpec
    ) -> dict[date, list[PortfolioPositionRow]]:
        """全部交易日候选目标权重。"""
        by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for r in factor_rows:
            d = _as_date(r.get("trading_date") or r.get("factor_date"))
            by_date[d].append(r)
        out: dict[date, list[PortfolioPositionRow]] = {}
        for d in sorted(by_date):
            rows = self.select_day(by_date[d], spec, trading_date=d)
            if rows:
                out[d] = rows
        return out

    def _selection_size(self, n: int, spec: PortfolioSpec) -> int:
        if spec.selection_mode == "TOP_N":
            return min(n, int(spec.top_n or 1))
        pct = float(spec.top_pct or 0.1)
        return max(1, min(n, int(math.ceil(n * pct))))

    def _quantile(
        self,
        items: list[dict[str, Any]],
        spec: PortfolioSpec,
        *,
        trading_date: date,
    ) -> list[PortfolioPositionRow]:
        n_g = int(spec.group_count)
        scores = [x["score"] for x in items]
        ranks = _average_ranks(scores)
        n = len(items)
        buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for item, rk in zip(items, ranks):
            g = _group_from_rank(rk, n, n_g)
            buckets[g].append(item)
        out: list[PortfolioPositionRow] = []
        for g in range(1, n_g + 1):
            chosen = buckets.get(g, [])
            if not chosen:
                continue
            # QUANTILE 审计权重：各分位等权（组内）
            ws = allocate_weights(
                [c["score"] for c in chosen],
                method="EQUAL_WEIGHT",
                sign=1.0,
            )
            for c, w in zip(chosen, ws):
                out.append(
                    PortfolioPositionRow(
                        trading_date=trading_date,
                        instrument_key=c["instrument_key"],
                        weight=float(w),
                        leg=f"Q{g}",
                        factor_value=c["factor_value"],
                    )
                )
        return out
