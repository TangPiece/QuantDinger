"""Phase 8E：可选读取 7C Controlled Live compare 索引。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.registry import ResearchRegistry

from ..protocol import MetricsSnapshot
from .metrics_inject import collect_from_inject


def collect_from_controlled_live(
    registry: ResearchRegistry,
    *,
    strategy_code: str,
    inject: dict[str, Any] | None = None,
) -> MetricsSnapshot:
    """优先 inject；否则从 controlled_live_compare_runs metadata 补 execution 指标。"""
    base = collect_from_inject(inject)
    if inject:
        return base
    try:
        rows = registry.list_controlled_live_compare_runs()  # type: ignore[attr-defined]
    except Exception:
        rows = []
    extra = dict(base.extra)
    for row in rows or []:
        meta = dict(getattr(row, "metadata", None) or {})
        if meta.get("strategy_code") == strategy_code:
            slip = meta.get("slippage_bps")
            reject = meta.get("reject_rate")
            updates: dict[str, Any] = {"extra": {**extra, "cl_compare_run_id": getattr(row, "run_id", "")}}
            if slip is not None:
                updates["slippage_bps"] = float(slip)
            if reject is not None:
                updates["reject_rate"] = float(reject)
            return base.model_copy(update=updates)
    return base


__all__ = ["collect_from_controlled_live"]
