"""Model Evaluation 指标：IC/RankIC（与 4D 语义对齐）+ Ranking@K + 薄 Stability。"""

from __future__ import annotations

from collections import defaultdict
from math import isfinite, sqrt
from statistics import mean, pstdev
from typing import Any, Mapping

from .protocol import LayerStatus, ModelEvaluationPolicy, ModelMetric


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = sqrt(sum((x - mx) ** 2 for x in xs))
    deny = sqrt(sum((y - my) ** 2 for y in ys))
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def _rank(vals: list[float]) -> list[float]:
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    for r, i in enumerate(order, start=1):
        ranks[i] = float(r)
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    return _pearson(_rank(xs), _rank(ys))


def _tstat(xs: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    m = mean(xs)
    s = pstdev(xs)
    if s == 0:
        return None
    return m / (s / sqrt(len(xs)))


def _ir(xs: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    s = pstdev(xs)
    if s == 0:
        return None
    return mean(xs) / s


def daily_ic_series(
    rows: list[Mapping[str, Any]], *, min_cs: int = 3
) -> tuple[list[float], list[float]]:
    """按 date 横截面 IC / RankIC。"""
    by_date: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        if row.get("label") is None:
            continue
        try:
            p = float(row["prediction"])
            y = float(row["label"])
        except (TypeError, ValueError, KeyError):
            continue
        if not (isfinite(p) and isfinite(y)):
            continue
        by_date[str(row.get("date") or "")].append((p, y))

    ics: list[float] = []
    rics: list[float] = []
    for _d, pairs in sorted(by_date.items()):
        if len(pairs) < min_cs:
            continue
        xs = [a for a, _ in pairs]
        ys = [b for _, b in pairs]
        ic = _pearson(xs, ys)
        ric = _spearman(xs, ys)
        if ic is not None and isfinite(ic):
            ics.append(ic)
        if ric is not None and isfinite(ric):
            rics.append(ric)
    return ics, rics


def compute_predictive_metrics(
    rows: list[Mapping[str, Any]], *, policy: ModelEvaluationPolicy
) -> dict[str, Any]:
    ics, rics = daily_ic_series(rows, min_cs=policy.min_cross_section)
    out: dict[str, Any] = {
        "mean_ic": mean(ics) if ics else None,
        "mean_rank_ic": mean(rics) if rics else None,
        "ic_ir": _ir(ics),
        "ic_t_stat": _tstat(ics),
        "positive_ic_ratio": (
            sum(1 for x in ics if x > 0) / len(ics) if ics else None
        ),
        "rank_ic_ir": _ir(rics),
        "rank_ic_t_stat": _tstat(rics),
        "positive_rank_ic_ratio": (
            sum(1 for x in rics if x > 0) / len(rics) if rics else None
        ),
        "n_ic_days": len(ics),
        "n_rank_ic_days": len(rics),
    }
    return out


def compute_ranking_at_k(
    rows: list[Mapping[str, Any]], *, ks: list[int]
) -> dict[str, Any]:
    """按 date：预测 Top-K 与 label Top-K 的 Precision / HitRate。"""
    by_date: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        if row.get("label") is None:
            continue
        try:
            p = float(row["prediction"])
            y = float(row["label"])
        except (TypeError, ValueError, KeyError):
            continue
        by_date[str(row.get("date") or "")].append((p, y))

    result: dict[str, Any] = {"ndcg": {"status": "SKIPPED"}, "by_k": {}}
    if not by_date:
        return result

    for k in ks:
        precisions: list[float] = []
        hits: list[float] = []
        for pairs in by_date.values():
            if len(pairs) < k:
                continue
            pred_top = {
                i
                for i, _ in sorted(
                    enumerate(pairs), key=lambda t: t[1][0], reverse=True
                )[:k]
            }
            label_top = {
                i
                for i, _ in sorted(
                    enumerate(pairs), key=lambda t: t[1][1], reverse=True
                )[:k]
            }
            inter = len(pred_top & label_top)
            precisions.append(inter / k)
            hits.append(1.0 if inter > 0 else 0.0)
        result["by_k"][str(k)] = {
            "precision_at_k": mean(precisions) if precisions else None,
            "hit_rate_at_k": mean(hits) if hits else None,
            "n_days": len(precisions),
        }
    return result


def compute_stability_profile(
    rows: list[Mapping[str, Any]], *, min_cs: int = 3
) -> dict[str, Any]:
    """按年切片 mean_ic（薄 profile）；regime 占位 SKIPPED。"""
    by_date: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        if row.get("label") is None:
            continue
        try:
            p = float(row["prediction"])
            y = float(row["label"])
        except (TypeError, ValueError, KeyError):
            continue
        by_date[str(row.get("date") or "")].append((p, y))

    by_year: dict[str, list[float]] = defaultdict(list)
    for d, pairs in by_date.items():
        if len(pairs) < min_cs:
            continue
        xs = [a for a, _ in pairs]
        ys = [b for _, b in pairs]
        ic = _pearson(xs, ys)
        if ic is None:
            continue
        year = d[:4] if len(d) >= 4 else "unknown"
        by_year[year].append(ic)

    yearly = {y: mean(vs) for y, vs in sorted(by_year.items()) if vs}
    return {
        "ic_by_year": yearly,
        "regime": {"status": "SKIPPED"},
    }


def build_metric_list(raw: dict[str, Any]) -> list[ModelMetric]:
    keys = (
        "mean_ic",
        "mean_rank_ic",
        "ic_ir",
        "ic_t_stat",
        "positive_ic_ratio",
    )
    out: list[ModelMetric] = []
    for k in keys:
        v = raw.get(k)
        status: LayerStatus = "PASS" if v is not None else "SKIPPED"
        out.append(ModelMetric(name=k, value=v if v is None else float(v), status=status))
    return out


def summarize_layer_statuses(
    *,
    quality: LayerStatus,
    predictive: dict[str, Any],
    ranking: dict[str, Any],
    stability: dict[str, Any],
) -> dict[str, LayerStatus]:
    pred_status: LayerStatus = "FAIL"
    mic = predictive.get("mean_ic")
    mric = predictive.get("mean_rank_ic")
    if mic is None and mric is None:
        pred_status = "SKIPPED"
    elif (mic is not None and mic > 0) or (mric is not None and mric > 0):
        pred_status = "PASS"
    elif (mic is not None and mic > -0.02) or (mric is not None and mric > -0.02):
        pred_status = "WARNING"
    else:
        pred_status = "FAIL"

    rank_status: LayerStatus = "SKIPPED"
    by_k = ranking.get("by_k") or {}
    if by_k:
        vals = [
            v.get("precision_at_k")
            for v in by_k.values()
            if v.get("precision_at_k") is not None
        ]
        if not vals:
            rank_status = "SKIPPED"
        elif mean(vals) >= 0.1:
            rank_status = "PASS"
        elif mean(vals) >= 0.05:
            rank_status = "WARNING"
        else:
            rank_status = "FAIL"

    stab_status: LayerStatus = "SKIPPED"
    yearly = stability.get("ic_by_year") or {}
    if yearly:
        ys = list(yearly.values())
        if all(v is not None and v > 0 for v in ys):
            stab_status = "PASS"
        elif any(v is not None and v < 0 for v in ys):
            stab_status = "WARNING"
        else:
            stab_status = "PASS"

    if quality == "BLOCKED":
        overall: LayerStatus = "BLOCKED"
    elif pred_status == "FAIL" or rank_status == "FAIL":
        overall = "FAIL"
    elif pred_status == "WARNING" or stab_status == "WARNING" or rank_status == "WARNING":
        overall = "WARNING"
    elif pred_status == "PASS":
        overall = "PASS"
    else:
        overall = "SKIPPED"

    return {
        "quality_status": quality,
        "predictive_status": pred_status,
        "stability_status": stab_status,
        "ranking_status": rank_status,
        "overall_status": overall,
    }


__all__ = [
    "build_metric_list",
    "compute_predictive_metrics",
    "compute_ranking_at_k",
    "compute_stability_profile",
    "daily_ic_series",
    "summarize_layer_statuses",
]
