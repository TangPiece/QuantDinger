"""Phase 3A：回测 Domain Contract（无引擎实现）。"""

from .engine import BacktestEngine
from .fingerprint import compute_request_fingerprint
from .ledger import EquityPoint, PortfolioSnapshot, PositionSnapshot, TradeRecord
from .policy import (
    BacktestMarketPricePolicy,
    CostPolicy,
    ExecutionPolicy,
    TradingRule,
)
from .presets import cn_equity_close_signal_next_open, research_qlib_relaxed
from .request import BacktestRequest
from .result import BacktestMetrics, BacktestResult
from .version import BACKTEST_CONTRACT_VERSION

__all__ = [
    "BACKTEST_CONTRACT_VERSION",
    "BacktestEngine",
    "BacktestMarketPricePolicy",
    "BacktestMetrics",
    "BacktestRequest",
    "BacktestResult",
    "CostPolicy",
    "EquityPoint",
    "ExecutionPolicy",
    "PortfolioSnapshot",
    "PositionSnapshot",
    "TradeRecord",
    "TradingRule",
    "cn_equity_close_signal_next_open",
    "compute_request_fingerprint",
    "research_qlib_relaxed",
]
