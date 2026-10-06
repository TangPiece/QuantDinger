"""Phase 5B：Research Backtest Engine（消费 5A Strategy Contract）。"""

from app.services.research_data.contracts import ResearchBacktestSummary

from .cost import ExecutionCostModel, NoCostModel
from .hash import compute_backtest_hash, normalize_backtest_spec
from .orchestrator import BacktestResult, ResearchBacktestError, ResearchBacktestService
from .protocol import (
    ENGINE_VERSION,
    EXECUTION_PROFILE_VERSION,
    RETURN_CALCULATION_VERSION,
    BacktestFrames,
    BacktestManifest,
    BacktestPositionRow,
    BacktestSpec,
    DailyReturnRow,
    NavPoint,
    PerformanceMetrics,
    ResearchExecutionPolicy,
    TurnoverRow,
)

__all__ = [
    "ENGINE_VERSION",
    "EXECUTION_PROFILE_VERSION",
    "RETURN_CALCULATION_VERSION",
    "BacktestFrames",
    "BacktestManifest",
    "BacktestPositionRow",
    "BacktestResult",
    "BacktestSpec",
    "DailyReturnRow",
    "ExecutionCostModel",
    "NavPoint",
    "NoCostModel",
    "PerformanceMetrics",
    "ResearchBacktestError",
    "ResearchBacktestService",
    "ResearchBacktestSummary",
    "ResearchExecutionPolicy",
    "TurnoverRow",
    "compute_backtest_hash",
    "normalize_backtest_spec",
]
