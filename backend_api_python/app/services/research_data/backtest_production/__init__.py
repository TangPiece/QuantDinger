"""Phase 3D：QuantDinger Production Backtest（独立于 Qlib）。"""

from .artifact_store import ProductionArtifactStore, compute_result_id
from .engine import ProductionBacktestEngine, ProductionBacktestError
from .market_loader import MarketPanel, load_market_panel, market_panel_from_bars
from .signal_loader import load_targets_by_date, targets_for_day
from .version import PRODUCTION_BACKTEST_ENGINE_VERSION

__all__ = [
    "PRODUCTION_BACKTEST_ENGINE_VERSION",
    "MarketPanel",
    "ProductionArtifactStore",
    "ProductionBacktestEngine",
    "ProductionBacktestError",
    "compute_result_id",
    "load_market_panel",
    "load_targets_by_date",
    "market_panel_from_bars",
    "targets_for_day",
]
