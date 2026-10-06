"""Phase 5D：Qlib Strategy Adapter（可替换 Research Engine）。"""

from app.services.research_data.contracts import QlibRunSummary

from .compatibility import assess_compatibility
from .hash import compute_qlib_run_hash, normalize_qlib_strategy_spec
from .portfolio_adapter import targets_to_weight_series, weights_close_to
from .protocol import (
    ENGINE_VERSION,
    CompatibilityReport,
    QlibStrategySpec,
    StrategyPlan,
)
from .runner import QlibRunResult, QlibStrategyError, QlibStrategyService
from .signal_adapter import prediction_close_to, to_prediction_series

__all__ = [
    "ENGINE_VERSION",
    "CompatibilityReport",
    "QlibRunResult",
    "QlibRunSummary",
    "QlibStrategyError",
    "QlibStrategyService",
    "QlibStrategySpec",
    "StrategyPlan",
    "assess_compatibility",
    "compute_qlib_run_hash",
    "normalize_qlib_strategy_spec",
    "prediction_close_to",
    "targets_to_weight_series",
    "to_prediction_series",
    "weights_close_to",
]
