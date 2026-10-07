"""Phase 8F：只读 8E latest_drift_scalars。"""

from __future__ import annotations

from typing import Any, Mapping


def load_feedback_scalars(feedback: Any | None, *, strategy_code: str) -> dict[str, float]:
    """不触发 8E 重算，仅读已有 comparison 摘要。"""
    if feedback is None:
        return {}
    try:
        scalars = feedback.latest_drift_scalars(strategy_code)
    except Exception:
        return {}
    return {k: float(v) for k, v in dict(scalars or {}).items()}


def drift_view(scalars: Mapping[str, float]) -> dict[str, Any]:
    """Dashboard drift 片段。"""
    return {
        "shadow_drift": float(scalars.get("shadow_drift", 0.0)),
        "max_drawdown": float(scalars.get("max_drawdown", 0.0)),
        "signal_correlation": float(scalars.get("signal_correlation", 1.0)),
        "drift_critical": bool(scalars.get("drift_critical", 0.0) >= 1.0),
    }


__all__ = ["drift_view", "load_feedback_scalars"]
