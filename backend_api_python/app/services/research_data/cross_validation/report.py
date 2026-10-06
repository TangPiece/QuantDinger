"""组装 CrossValidationReport 与整体 status。"""

from __future__ import annotations

from typing import Any, Sequence

from .kinds import CvStatus
from .protocol import (
    AttributionBreakdown,
    CrossValidationReport,
    ENGINE_VERSION,
    LayerResult,
)


def aggregate_status(
    layers: Sequence[LayerResult],
    attribution: AttributionBreakdown,
    *,
    realism: str,
    other_tol: float,
) -> CvStatus:
    """聚合层结果 → PASSED / FAILED / PASSED_WITH_EXPECTED_DIFF。"""
    hard_fail = any(L.status == "FAIL" for L in layers)
    if hard_fail:
        return "FAILED"
    if abs(attribution.other) > other_tol and "unexplained" in " ".join(
        attribution.notes
    ):
        return "FAILED"
    has_expected = any(L.kind == "EXPECTED_DIFFERENCE" for L in layers)
    if realism == "NET" or has_expected or abs(attribution.cost) > 0:
        return "PASSED_WITH_EXPECTED_DIFF"
    return "PASSED"


def build_report(
    *,
    cv_hash: str,
    strategy_hash: str,
    backtest_hash: str,
    qlib_run_hash: str,
    start_date: str,
    end_date: str,
    realism: str,
    layers: Sequence[LayerResult],
    attribution: AttributionBreakdown,
    side_by_side: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    other_tol: float = 1e-3,
) -> CrossValidationReport:
    """生成完整报告。"""
    status = aggregate_status(
        layers, attribution, realism=realism, other_tol=other_tol
    )
    return CrossValidationReport(
        cv_hash=cv_hash,
        strategy_hash=strategy_hash,
        backtest_hash=backtest_hash,
        qlib_run_hash=qlib_run_hash,
        start_date=start_date,
        end_date=end_date,
        realism=realism,
        status=status,
        layers=list(layers),
        attribution=attribution,
        side_by_side=side_by_side,
        engine_version=ENGINE_VERSION,
        metadata=dict(metadata or {}),
    )
