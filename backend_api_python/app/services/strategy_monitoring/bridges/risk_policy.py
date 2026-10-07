"""Phase 8F：只读 RiskPolicy 限额（不算 RiskEngine 判定）。"""

from __future__ import annotations

from typing import Any, Mapping


def load_risk_limits(risk: Any | None, *, strategy_code: str) -> dict[str, float]:
    if risk is None:
        return {"max_gross_exposure": 1.0, "max_turnover": 0.30}
    try:
        policy = risk.get_policy(strategy_code, "1")
    except Exception:
        try:
            policy = risk.get_policy("default", "1")
        except Exception:
            return {"max_gross_exposure": 1.0, "max_turnover": 0.30}
    return {
        "max_gross_exposure": float(getattr(policy, "max_gross_exposure", 1.0) or 1.0),
        "max_turnover": float(getattr(policy, "max_turnover", 0.30) or 0.30),
    }


def risk_view(metrics: Mapping[str, float]) -> dict[str, Any]:
    return {
        "gross_exposure_util": float(metrics.get("gross_exposure_util", 0.0)),
        "turnover_util": float(metrics.get("turnover_util", 0.0)),
    }


__all__ = ["load_risk_limits", "risk_view"]
