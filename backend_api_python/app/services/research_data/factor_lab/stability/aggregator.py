"""StabilityFrames → FactorStabilitySummary（每 horizon 一条；无综合 score）。"""

from __future__ import annotations

import math
from statistics import mean, stdev
from typing import Any, Literal, Optional

from app.services.research_data.contracts import FactorStabilitySummary

from .protocol import STABILITY_VERSION, StabilityFrames, StabilitySpec


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
    """ICIR = mean / sample_std (ddof=1)，与 4D 一致。"""
    if len(vals) < 2:
        return None
    s = stdev(vals)
    if s == 0.0:
        return None
    return mean(vals) / s


class StabilityAggregator:
    """按 horizon 打包 JSON 汇总字段。"""

    def aggregate(
        self,
        frames: StabilityFrames,
        spec: StabilitySpec,
        *,
        factor_dataset_id: str = "",
        direction: Literal["POSITIVE", "NEGATIVE"] = "POSITIVE",
    ) -> list[FactorStabilitySummary]:
        horizons = frames.horizons or sorted(
            {int(p.horizon) for p in frames.metric_points}
        )
        out: list[FactorStabilitySummary] = []
        for h in horizons:
            pts = [
                p
                for p in frames.metric_points
                if int(p.horizon) == h and p.valid
            ]
            ics = _finite([p.ic for p in pts])
            rics = _finite([p.rank_ic for p in pts])

            roll_h = [r for r in frames.rolling_ic if int(r.horizon) == h]
            best_worst: dict[str, Any] = {}
            for w in spec.rolling_windows:
                means = _finite(
                    [r.ic_mean for r in roll_h if int(r.window) == int(w)]
                )
                best_worst[str(w)] = {
                    "best_ic_mean": max(means) if means else None,
                    "worst_ic_mean": min(means) if means else None,
                }

            dist_h = [
                d.model_dump(mode="json")
                for d in frames.distributions
                if int(d.horizon) == h
            ]
            decay_h = [
                d.model_dump(mode="json")
                for d in frames.decay
                if int(d.horizon) == h
            ]
            # Decay 曲线是跨 horizon 的；每条 summary 仍附带全曲线便于查询
            decay_all = [d.model_dump(mode="json") for d in frames.decay]
            regime_h = [
                r.model_dump(mode="json")
                for r in frames.regime
                if int(r.horizon) == h
            ]
            gst_h = [
                g
                for g in frames.group_stability
                if int(g.horizon) == h
            ]
            # 全样本 group 稳定性摘要：各 portfolio 末窗均值
            group_metrics: dict[str, Any] = {}
            for port in ("TOP", "BOTTOM", "LONG", "SHORT", "LONG_SHORT"):
                rows = [g for g in gst_h if g.portfolio == port]
                means = _finite([g.mean_return for g in rows])
                group_metrics[port] = {
                    "mean_of_rolling_means": mean(means) if means else None,
                    "positive_ratio_of_rolling": (
                        sum(1 for v in means if v > 0) / len(means) if means else None
                    ),
                    "row_count": len(rows),
                }

            ic_metrics = {
                "ic_mean": mean(ics) if ics else None,
                "ic_std": stdev(ics) if len(ics) >= 2 else None,
                "ic_ir": _ir(ics),
                "ic_positive_ratio": (
                    sum(1 for v in ics if v > 0) / len(ics) if ics else None
                ),
                "ic_negative_ratio": (
                    sum(1 for v in ics if v < 0) / len(ics) if ics else None
                ),
                "rankic_mean": mean(rics) if rics else None,
                "rank_ic_ir": _ir(rics),
                "distributions": dist_h,
                "best_worst_rolling": best_worst,
                "valid_day_count": len(pts),
            }

            out.append(
                FactorStabilitySummary(
                    stability_hash=frames.stability_hash,
                    evaluation_hash=frames.evaluation_hash,
                    factor_dataset_id=factor_dataset_id,
                    horizon=int(h),
                    rolling_windows_json=list(spec.rolling_windows),
                    decay_summary_json=decay_all if int(h) == horizons[0] else decay_h,
                    regime_summary_json=regime_h,
                    ic_stability_metrics_json=ic_metrics,
                    group_stability_metrics_json=group_metrics,
                    stability_version=spec.stability_version or STABILITY_VERSION,
                    metadata={
                        "direction": direction,
                        "regime_types": list(spec.regime_types),
                    },
                )
            )
        return out
