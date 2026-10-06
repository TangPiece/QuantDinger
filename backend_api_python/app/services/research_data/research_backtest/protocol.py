"""Phase 5B：Research Backtest Domain（研究回测，非生产撮合）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import Field, field_validator, model_validator

from app.services.research_data.contracts import ResearchBacktestSummary, _ContractModel

ENGINE_VERSION = "qd_research_backtest@1"
RETURN_CALCULATION_VERSION = "research_nav@1"

ExecutionMode = Literal["NEXT_OPEN", "NEXT_CLOSE", "SAME_CLOSE"]
BenchmarkMode = Literal["NONE", "INDEX", "CUSTOM"]
MissingPricePolicy = Literal["SKIP_TO_CASH"]


class ResearchExecutionPolicy(_ContractModel):
    """最小执行语义：信号日 → 执行日 + 成交价字段。"""

    mode: ExecutionMode = "NEXT_OPEN"

    @property
    def fill_field(self) -> str:
        """成交价取 open 或 close。"""
        if self.mode == "NEXT_OPEN":
            return "open"
        return "close"

    @property
    def allows_same_close(self) -> bool:
        return self.mode == "SAME_CLOSE"


class BacktestSpec(_ContractModel):
    """研究回测规格：钉住 strategy + 窗口 + 执行/基准策略。"""

    strategy_hash: str
    start_date: date
    end_date: date
    execution_policy: ResearchExecutionPolicy = Field(
        default_factory=ResearchExecutionPolicy
    )
    benchmark_mode: BenchmarkMode = "NONE"
    benchmark_instrument_key: str = ""
    initial_nav: float = 1.0
    missing_price_policy: MissingPricePolicy = "SKIP_TO_CASH"
    exchange: str = "CN"
    engine_version: str = ENGINE_VERSION
    return_calculation_version: str = RETURN_CALCULATION_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("strategy_hash")
    @classmethod
    def _shash(cls, v: str) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("strategy_hash required")
        return s

    @field_validator("initial_nav")
    @classmethod
    def _nav(cls, v: float) -> float:
        if float(v) <= 0:
            raise ValueError("initial_nav must be > 0")
        return float(v)

    @model_validator(mode="after")
    def _window_and_benchmark(self) -> "BacktestSpec":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        if self.benchmark_mode == "INDEX" and not (
            self.benchmark_instrument_key or ""
        ).strip():
            raise ValueError(
                "benchmark_instrument_key required when benchmark_mode=INDEX"
            )
        return self


class NavPoint(_ContractModel):
    """日终 NAV。"""

    trading_date: date
    nav: float
    cash: float = 0.0
    gross_exposure: float = 0.0


class DailyReturnRow(_ContractModel):
    """日收益行。"""

    trading_date: date
    portfolio_return: Optional[float] = None
    benchmark_return: Optional[float] = None
    excess_return: Optional[float] = None


class BacktestPositionRow(_ContractModel):
    """日终持仓行。"""

    trading_date: date
    instrument_key: str
    shares: float
    weight: float = 0.0
    price: float = 0.0


class TurnoverRow(_ContractModel):
    """调仓换手行。"""

    trading_date: date
    turnover: Optional[float] = None
    rebalanced: bool = False


class PerformanceMetrics(_ContractModel):
    """研究回测绩效摘要（252 日年化口径）。"""

    total_return: Optional[float] = None
    annualized_return: Optional[float] = None
    annualized_volatility: Optional[float] = None
    sharpe: Optional[float] = None
    max_drawdown: Optional[float] = None
    calmar: Optional[float] = None
    win_rate: Optional[float] = None
    mean_turnover: Optional[float] = None
    n_days: int = 0
    n_rebalances: int = 0


class BacktestFrames(_ContractModel):
    """回测内存帧。"""

    backtest_hash: str
    strategy_hash: str = ""
    nav: list[NavPoint] = Field(default_factory=list)
    returns: list[DailyReturnRow] = Field(default_factory=list)
    positions: list[BacktestPositionRow] = Field(default_factory=list)
    turnover: list[TurnoverRow] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    benchmark_metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BacktestManifest(_ContractModel):
    """回测产物清单。"""

    backtest_hash: str
    strategy_hash: str = ""
    start_date: str = ""
    end_date: str = ""
    execution_policy: str = "NEXT_OPEN"
    allows_same_close: bool = False
    engine_version: str = ENGINE_VERSION
    return_calculation_version: str = RETURN_CALCULATION_VERSION
    nav_rows: int = 0
    return_rows: int = 0
    position_rows: int = 0
    checksum: str = ""
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ENGINE_VERSION",
    "RETURN_CALCULATION_VERSION",
    "BacktestFrames",
    "BacktestManifest",
    "BacktestPositionRow",
    "BacktestSpec",
    "DailyReturnRow",
    "NavPoint",
    "PerformanceMetrics",
    "ResearchBacktestSummary",
    "ResearchExecutionPolicy",
    "TurnoverRow",
]
