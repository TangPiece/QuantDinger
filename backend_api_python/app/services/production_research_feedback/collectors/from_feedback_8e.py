"""Phase 8H：从 8E Performance Feedback registry 工件只读采集。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.registry import ResearchRegistry

from ..protocol import FeedbackLineage, FeedbackRow


def collect_from_feedback_8e(
    registry: ResearchRegistry,
    *,
    strategy_code: str,
    feedback_8e: Any | None = None,
) -> tuple[list[FeedbackRow], FeedbackLineage]:
    rows: list[FeedbackRow] = []
    lineage = FeedbackLineage()
    code = str(strategy_code or "").strip()
    try:
        runs = registry.list_performance_comparison_runs(code)
    except Exception:
        runs = []
    if runs:
        run = runs[-1]
        lineage = FeedbackLineage(
            comparison_run_id=run.run_id,
            dataset_hash=run.baseline_id or "",
            strategy_version="",
        )
        # 从 actual_metrics_json 取常用字段
        metrics = run.actual_metrics_json or {}
        for key in ("return_total", "sharpe", "slippage_bps"):
            if key in metrics:
                rows.append(
                    FeedbackRow(
                        row_id=f"8e_{run.run_id}_{key}",
                        metric=key,
                        value=float(metrics[key]),
                        as_of_time=run.completed_at or "",
                        source_artifact_id=run.run_id,
                        source_phase="8E",
                    )
                )
    del feedback_8e  # 预留 service 桥，P0 以 registry 为准
    return rows, lineage
