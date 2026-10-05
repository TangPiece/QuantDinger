"""BacktestResult 与 Metrics 契约（数值由引擎在 3B+ 填充）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from app.services.research_data.contracts import _ContractModel

from .ledger import EquityPoint, PortfolioSnapshot, PositionSnapshot, TradeRecord


class BacktestMetrics(_ContractModel):
    """统一指标名；两引擎允许数值不同（3E 对比）。"""

    total_return: Optional[float] = None
    annualized_return: Optional[float] = None
    volatility: Optional[float] = None
    sharpe: Optional[float] = None
    sortino: Optional[float] = None
    max_drawdown: Optional[float] = None
    calmar: Optional[float] = None
    turnover: Optional[float] = None
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None


class BacktestResult(_ContractModel):
    """引擎无关的回测输出；禁止直接暴露 Qlib 原生对象。"""

    result_id: str
    request_fingerprint: str
    experiment_id: str
    dataset_hash: str
    engine: Literal["qlib", "production"]
    engine_version: Optional[str] = None
    contract_version: str = ""
    equity_curve: list[EquityPoint] = []
    trades: list[TradeRecord] = []
    position_history: list[PositionSnapshot] = []
    portfolio_history: list[PortfolioSnapshot] = []
    metrics: BacktestMetrics = Field(default_factory=BacktestMetrics)
    artifact_uris: dict[str, str] = {}
    metadata: dict[str, Any] = {}
