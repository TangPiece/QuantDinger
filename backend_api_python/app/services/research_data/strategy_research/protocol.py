"""Phase 5A：Strategy Research Domain（契约物化，非 Backtest）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field, field_validator, model_validator

from app.services.research_data.contracts import (
    Signal,
    StrategyResearchSummary,
    TargetPosition,
    _ContractModel,
)

STRATEGY_VERSION = "qd_strategy_research@1"
SIGNAL_VERSION = "qd_strategy_signal@1"
TIMING_CN_DAILY_T1 = "CN_DAILY_T1_OPEN"

DirectionMode = Literal["SIGN_OF_SCORE", "LONG_IF_POSITIVE"]
RankMethod = Literal["AVERAGE_RANK"]
SignalSource = Literal["FACTOR_DATASET"]
RebalanceFrequency = Literal["DAILY", "WEEKLY", "MONTHLY"]
RebalanceDay = Literal["FIRST_IN_PERIOD", "LAST_IN_PERIOD", "FRIDAY"]
RebalanceTime = Literal["CLOSE"]
HoldingMode = Literal["HOLD_UNTIL_NEXT_REBALANCE"]


class SignalDefinition(_ContractModel):
    """因子 → Signal 的映射定义（v1 仅 FactorDataset）。"""

    source: SignalSource = "FACTOR_DATASET"
    factor_dataset_id: str
    direction_mode: DirectionMode = "SIGN_OF_SCORE"
    score_field: str = "value"
    rank_method: RankMethod = "AVERAGE_RANK"
    signal_version: str = SIGNAL_VERSION


class RebalanceRule(_ContractModel):
    """调仓规则声明（须与 4I rebalance_frequency 一致）。"""

    frequency: RebalanceFrequency = "DAILY"
    rebalance_day: RebalanceDay = "FIRST_IN_PERIOD"
    rebalance_time: RebalanceTime = "CLOSE"

    @model_validator(mode="after")
    def _defaults(self) -> "RebalanceRule":
        # WEEKLY 默认周五；MONTHLY 默认期末
        if self.frequency == "WEEKLY" and self.rebalance_day == "FIRST_IN_PERIOD":
            object.__setattr__(self, "rebalance_day", "FRIDAY")
        if self.frequency == "MONTHLY" and self.rebalance_day == "FIRST_IN_PERIOD":
            object.__setattr__(self, "rebalance_day", "LAST_IN_PERIOD")
        if self.rebalance_time != "CLOSE":
            raise ValueError("rebalance_time only CLOSE in 5A v1")
        return self


class HoldingRule(_ContractModel):
    """持仓规则；v1 仅持有至下次调仓。"""

    mode: HoldingMode = "HOLD_UNTIL_NEXT_REBALANCE"


class StrategySpec(_ContractModel):
    """策略研究规格：因子 Signal + 4I Portfolio 引用。"""

    strategy_code: str
    strategy_name: str = ""
    factor_dataset_id: str
    portfolio_hash: str
    signal_definition: Optional[SignalDefinition] = None
    rebalance_rule: RebalanceRule = Field(default_factory=RebalanceRule)
    holding_rule: HoldingRule = Field(default_factory=HoldingRule)
    universe_code: str = ""
    snapshot_id: str = ""
    timing_profile: str = TIMING_CN_DAILY_T1
    strategy_version: str = STRATEGY_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("strategy_code")
    @classmethod
    def _code(cls, v: str) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("strategy_code required")
        return s

    @field_validator("portfolio_hash")
    @classmethod
    def _phash(cls, v: str) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("portfolio_hash required")
        return s

    @model_validator(mode="after")
    def _sync_signal(self) -> "StrategySpec":
        if self.signal_definition is None:
            object.__setattr__(
                self,
                "signal_definition",
                SignalDefinition(factor_dataset_id=self.factor_dataset_id),
            )
        elif self.signal_definition.factor_dataset_id != self.factor_dataset_id:
            object.__setattr__(
                self,
                "signal_definition",
                self.signal_definition.model_copy(
                    update={"factor_dataset_id": self.factor_dataset_id}
                ),
            )
        if self.timing_profile != TIMING_CN_DAILY_T1:
            raise ValueError("timing_profile only CN_DAILY_T1_OPEN in 5A v1")
        if self.holding_rule.mode != "HOLD_UNTIL_NEXT_REBALANCE":
            raise ValueError("holding_rule.mode only HOLD_UNTIL_NEXT_REBALANCE in v1")
        return self


class StrategyFrames(_ContractModel):
    """物化帧。"""

    strategy_hash: str
    strategy_code: str = ""
    signals: list[Signal] = Field(default_factory=list)
    positions: list[TargetPosition] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyManifest(_ContractModel):
    strategy_hash: str
    strategy_code: str = ""
    factor_dataset_id: str = ""
    portfolio_hash: str = ""
    strategy_spec: dict[str, Any] = Field(default_factory=dict)
    signal_rows: int = 0
    position_rows: int = 0
    checksum: str = ""
    strategy_version: str = STRATEGY_VERSION
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "STRATEGY_VERSION",
    "SIGNAL_VERSION",
    "TIMING_CN_DAILY_T1",
    "HoldingRule",
    "RebalanceRule",
    "SignalDefinition",
    "StrategyFrames",
    "StrategyManifest",
    "StrategyResearchSummary",
    "StrategySpec",
]
