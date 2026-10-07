"""Phase 8E：可选读取 7B Shadow compare 索引（不替换 7B 服务）。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.registry import ResearchRegistry

from ..protocol import MetricsSnapshot
from .metrics_inject import collect_from_inject


def collect_from_shadow(
    registry: ResearchRegistry,
    *,
    strategy_code: str,
    inject: dict[str, Any] | None = None,
) -> MetricsSnapshot:
    """优先 inject；否则尝试从 shadow_compare_runs metadata 补 qty_delta。"""
    base = collect_from_inject(inject)
    if inject:
        return base
    try:
        rows = registry.list_shadow_compare_runs()  # type: ignore[attr-defined]
    except Exception:
        rows = []
    extra = dict(base.extra)
    for row in rows or []:
        meta = dict(getattr(row, "metadata", None) or {})
        if meta.get("strategy_code") == strategy_code:
            qd = meta.get("qty_delta")
            if qd is not None:
                extra["shadow_compare_run_id"] = getattr(row, "run_id", "")
                return base.model_copy(
                    update={
                        "qty_delta": float(qd),
                        "shadow_drift": float(meta.get("shadow_drift", base.shadow_drift)),
                        "extra": extra,
                    }
                )
    return base


__all__ = ["collect_from_shadow"]
