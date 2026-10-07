"""薄层 FactorQualityScore（raw 必存）。"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from .protocol import ENGINE_VERSION, FactorQualityScore


def _clamp01(x: float) -> float:
    if math.isnan(x) or math.isfinite(x) is False:
        return 0.0
    return max(0.0, min(1.0, x))


def _norm_ic(mean_ic: float | None) -> float:
    if mean_ic is None:
        return 0.0
    return _clamp01(abs(float(mean_ic)) / 0.05)


def _norm_icir(ic_ir: float | None) -> float:
    if ic_ir is None:
        return 0.0
    return _clamp01(abs(float(ic_ir)) / 2.0)


def _norm_stability(stab: float | None) -> float:
    if stab is None:
        return 0.5
    return _clamp01(float(stab))


def _norm_turnover(turnover: float | None) -> float:
    if turnover is None:
        return 0.5
    # 换手越低分越高
    return _clamp01(1.0 - min(float(turnover), 1.0))


def _norm_cost(cost: float | None) -> float:
    if cost is None:
        return 0.7
    return _clamp01(1.0 - min(abs(float(cost)) * 100.0, 1.0))


def compute_quality_score(
    *,
    evaluation_id: str,
    run_content_hash: str,
    raw_metrics: dict[str, Any],
    primary_horizon: int = 1,
) -> FactorQualityScore:
    """加权子分；总分非唯一真相，raw_metrics 一并写入。"""
    hkey = str(primary_horizon)
    ic_block = (raw_metrics.get("ic_by_horizon") or {}).get(hkey) or {}
    grp_block = (raw_metrics.get("group_by_horizon") or {}).get(hkey) or {}
    stab_block = (raw_metrics.get("stability_by_horizon") or {}).get(hkey) or {}

    ic_score = _norm_ic(ic_block.get("mean_ic"))
    icir_score = _norm_icir(ic_block.get("ic_ir"))
    stability_score = _norm_stability(stab_block.get("ic_stability"))
    turnover_score = _norm_turnover(grp_block.get("turnover"))
    cost_score = _norm_cost(grp_block.get("estimated_cost"))

    weights = (0.30, 0.25, 0.20, 0.15, 0.10)
    subs = (ic_score, icir_score, stability_score, turnover_score, cost_score)
    total = sum(w * s for w, s in zip(weights, subs))

    return FactorQualityScore(
        engine_version=ENGINE_VERSION,
        evaluation_id=evaluation_id,
        run_content_hash=run_content_hash,
        total_score=round(total, 6),
        ic_score=round(ic_score, 6),
        icir_score=round(icir_score, 6),
        stability_score=round(stability_score, 6),
        turnover_score=round(turnover_score, 6),
        cost_score=round(cost_score, 6),
        raw_metrics=dict(raw_metrics),
        published_at=datetime.now(timezone.utc),
    )


__all__ = ["compute_quality_score"]
