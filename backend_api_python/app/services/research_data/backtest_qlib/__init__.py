"""Phase 3B：Qlib Research Backtest 适配器（独立包，避免污染 backtest/ AST 约束）。"""

from .artifact_store import BacktestArtifactStore, compute_result_id
from .engine import QlibBacktestError, QlibResearchBacktestEngine, request_from_experiment
from .exchange_map import map_exchange_kwargs
from .signal_loader import load_target_weight_series, weights_for_date
from .version import QLIB_BACKTEST_ENGINE_VERSION
from .weight_strategy import QuantDingerWeightStrategy

__all__ = [
    "QLIB_BACKTEST_ENGINE_VERSION",
    "BacktestArtifactStore",
    "QlibBacktestError",
    "QlibResearchBacktestEngine",
    "QuantDingerWeightStrategy",
    "compute_result_id",
    "load_target_weight_series",
    "map_exchange_kwargs",
    "request_from_experiment",
    "weights_for_date",
]
