"""按日横截面 Pearson IC / Spearman RankIC（永不 abs）。"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any, Protocol, Sequence, runtime_checkable

import pandas as pd

from .protocol import MetricPoint, MetricSpec, MetricTimeSeries

_FORWARD_RE = re.compile(r"^forward_return_(\d+)d$")


def infer_horizons(records: Sequence[dict[str, Any]]) -> list[int]:
    """从 evaluation 行推断 forward_return_{N}d 列。"""
    found: set[int] = set()
    for r in records:
        for k in r:
            m = _FORWARD_RE.match(str(k))
            if m:
                found.add(int(m.group(1)))
    return sorted(found)


def _as_date(v: Any) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if hasattr(v, "date") and not isinstance(v, date):
        return v.date()
    return date.fromisoformat(str(v)[:10])


def _is_nan(v: Any) -> bool:
    if v is None:
        return True
    try:
        f = float(v)
        return math.isnan(f)
    except (TypeError, ValueError):
        return True


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """手写 Pearson，避免常数序列返回 0。"""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = 0.0
    dx2 = 0.0
    dy2 = 0.0
    for x, y in zip(xs, ys):
        dx = x - mx
        dy = y - my
        num += dx * dy
        dx2 += dx * dx
        dy2 += dy * dy
    if dx2 <= 0.0 or dy2 <= 0.0:
        return None
    return num / math.sqrt(dx2 * dy2)


def _rank(values: list[float]) -> list[float]:
    """平均秩（Spearman 用）。"""
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


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    return _pearson(_rank(xs), _rank(ys))


@runtime_checkable
class CrossSectionalMetric(Protocol):
    """横截面指标协议。"""

    name: str

    def day_corr(self, factors: list[float], returns: list[float]) -> float | None:
        ...


class PearsonICCalculator:
    """Pearson IC。"""

    name = "pearson_ic"

    def day_corr(self, factors: list[float], returns: list[float]) -> float | None:
        return _pearson(factors, returns)


class SpearmanRankICCalculator:
    """Spearman RankIC。"""

    name = "spearman_rank_ic"

    def day_corr(self, factors: list[float], returns: list[float]) -> float | None:
        return _spearman(factors, returns)


class CrossSectionalICEngine:
    """按日 × horizon 计算 IC / RankIC 时间序列。"""

    def __init__(
        self,
        pearson: PearsonICCalculator | None = None,
        spearman: SpearmanRankICCalculator | None = None,
    ) -> None:
        self._pearson = pearson or PearsonICCalculator()
        self._spearman = spearman or SpearmanRankICCalculator()

    def calculate(
        self,
        records: Sequence[dict[str, Any]],
        spec: MetricSpec,
        *,
        metric_hash: str,
    ) -> MetricTimeSeries:
        """只消费 allowed_sample_status；永不 abs(ic)。"""
        allowed = set(spec.allowed_sample_status)
        horizons = list(spec.horizons) if spec.horizons else infer_horizons(records)
        if not horizons:
            return MetricTimeSeries(
                metric_hash=metric_hash,
                evaluation_hash=spec.evaluation_hash,
                horizons=[],
                points=[],
            )

        # 过滤 + 建 DF
        rows: list[dict[str, Any]] = []
        for r in records:
            if str(r.get("sample_status") or "") not in allowed:
                continue
            fv = r.get("factor_value", r.get("value"))
            if _is_nan(fv):
                continue
            item = {
                "factor_date": _as_date(r.get("factor_date") or r.get("evaluation_date")),
                "factor_value": float(fv),
            }
            for h in horizons:
                col = f"forward_return_{h}d"
                rv = r.get(col)
                item[col] = None if _is_nan(rv) else float(rv)
            rows.append(item)

        points: list[MetricPoint] = []
        if not rows:
            return MetricTimeSeries(
                metric_hash=metric_hash,
                evaluation_hash=spec.evaluation_hash,
                horizons=horizons,
                points=[],
            )

        df = pd.DataFrame(rows)
        for day, g in df.groupby("factor_date", sort=True):
            for h in horizons:
                col = f"forward_return_{h}d"
                sub = g[["factor_value", col]].dropna()
                n = int(len(sub))
                ic: float | None = None
                ric: float | None = None
                valid = False
                if n >= int(spec.min_cross_section_size):
                    xs = sub["factor_value"].astype(float).tolist()
                    ys = sub[col].astype(float).tolist()
                    ic = self._pearson.day_corr(xs, ys)
                    ric = self._spearman.day_corr(xs, ys)
                    # 常数序列 → None；不得写成 0
                    valid = ic is not None and ric is not None
                points.append(
                    MetricPoint(
                        evaluation_date=_as_date(day),
                        horizon=int(h),
                        ic=ic,
                        rank_ic=ric,
                        sample_count=n,
                        valid=valid,
                    )
                )

        return MetricTimeSeries(
            metric_hash=metric_hash,
            evaluation_hash=spec.evaluation_hash,
            horizons=horizons,
            points=points,
            metadata={"direction": spec.direction},
        )
