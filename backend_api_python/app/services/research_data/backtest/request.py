"""BacktestRequest：顶层回测输入契约。"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from app.services.research_data.contracts import ExperimentDefinition, _ContractModel

from .policy import (
    BacktestMarketPricePolicy,
    CostPolicy,
    ExecutionPolicy,
    TradingRule,
)
from .version import BACKTEST_CONTRACT_VERSION


class BacktestRequest(_ContractModel):
    """QuantDinger 回测请求；Qlib / Production 共用。"""

    experiment_id: str
    dataset_hash: str
    strategy_version: str
    start_date: str
    end_date: str
    initial_capital: float
    engine: Literal["qlib", "production"]
    execution_policy: ExecutionPolicy
    market_price_policy: BacktestMarketPricePolicy
    cost_policy: CostPolicy = Field(default_factory=CostPolicy)
    trading_rule: TradingRule = Field(default_factory=TradingRule)
    contract_version: str = BACKTEST_CONTRACT_VERSION
    signal_run_id: Optional[str] = None
    target_positions_artifact_id: Optional[str] = None
    universe_code: Optional[str] = None
    benchmark: Optional[str] = None
    frequency: str = "1d"
    seed: Optional[int] = None

    @classmethod
    def from_experiment(
        cls,
        experiment: ExperimentDefinition,
        *,
        start_date: str,
        end_date: str,
        initial_capital: float,
        engine: Literal["qlib", "production"],
        execution_policy: ExecutionPolicy,
        market_price_policy: BacktestMarketPricePolicy,
        cost_policy: CostPolicy | None = None,
        trading_rule: TradingRule | None = None,
        signal_run_id: str | None = None,
        target_positions_artifact_id: str | None = None,
    ) -> "BacktestRequest":
        """从 Registry Experiment 填追溯字段（不读 artifact 磁盘）。"""
        return cls(
            experiment_id=experiment.experiment_id,
            dataset_hash=experiment.dataset_hash,
            strategy_version=experiment.strategy_version or "",
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            engine=engine,
            execution_policy=execution_policy,
            market_price_policy=market_price_policy,
            cost_policy=cost_policy or CostPolicy(),
            trading_rule=trading_rule or TradingRule(),
            signal_run_id=signal_run_id or experiment.signal_run_id,
            target_positions_artifact_id=(
                target_positions_artifact_id or experiment.signal_artifact_id
            ),
        )
