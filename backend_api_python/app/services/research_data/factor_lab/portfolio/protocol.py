"""Phase 4I：Factor Portfolio Domain（目标持仓 + 理论绩效，非 Production Backtest）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import Field, field_validator, model_validator

from app.services.research_data.contracts import (
    FactorPortfolioSummary,
    _ContractModel,
)

PORTFOLIO_VERSION = "qd_factor_portfolio@1"
SCHEMA_POSITION = "portfolio_position@1"
SCHEMA_WEIGHT = "portfolio_weight@1"
SCHEMA_RETURN = "portfolio_return_daily@1"
SCHEMA_TURNOVER = "portfolio_turnover_daily@1"

ConstructionMethod = Literal["LONG_ONLY", "LONG_SHORT", "QUANTILE"]
WeightMethod = Literal["EQUAL_WEIGHT", "SCORE_WEIGHT", "RANK_WEIGHT"]
SelectionMode = Literal["TOP_N", "TOP_PCT"]
RebalanceFrequency = Literal["DAILY", "WEEKLY", "MONTHLY"]
Direction = Literal["POSITIVE", "NEGATIVE"]


class PortfolioSpec(_ContractModel):
    """因子组合构建规格；只读 FactorDataset + 4C Evaluation。"""

    factor_dataset_id: str
    evaluation_hash: str
    construction_method: ConstructionMethod = "LONG_ONLY"
    weight_method: WeightMethod = "EQUAL_WEIGHT"
    selection_mode: SelectionMode = "TOP_PCT"
    top_n: Optional[int] = None
    top_pct: Optional[float] = 0.1
    group_count: Literal[5, 10] = 5
    rebalance_frequency: RebalanceFrequency = "DAILY"
    horizon: int = 1
    min_turnover: float = 0.005
    min_cross_section_size: int = 30
    direction: Direction = "POSITIVE"
    portfolio_version: str = PORTFOLIO_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("horizon")
    @classmethod
    def _horizon(cls, v: int) -> int:
        if int(v) < 1:
            raise ValueError("horizon must be >= 1")
        return int(v)

    @field_validator("min_turnover")
    @classmethod
    def _min_to(cls, v: float) -> float:
        if float(v) < 0:
            raise ValueError("min_turnover must be >= 0")
        return float(v)

    @field_validator("min_cross_section_size")
    @classmethod
    def _min_cs(cls, v: int) -> int:
        if int(v) < 2:
            raise ValueError("min_cross_section_size must be >= 2")
        return int(v)

    @model_validator(mode="after")
    def _validate(self) -> "PortfolioSpec":
        if self.construction_method == "QUANTILE":
            return self
        if self.selection_mode == "TOP_N":
            if self.top_n is None or int(self.top_n) < 1:
                raise ValueError("TOP_N requires top_n >= 1")
        elif self.selection_mode == "TOP_PCT":
            if self.top_pct is None:
                raise ValueError("TOP_PCT requires top_pct")
            pct = float(self.top_pct)
            # LONG_SHORT 两端各取 pct，故上限 0.5；LONG_ONLY 允许到 1.0
            upper = 0.5 if self.construction_method == "LONG_SHORT" else 1.0
            if not (0.0 < pct <= upper):
                raise ValueError(f"top_pct must be in (0, {upper}]")
        return self


class PortfolioPositionRow(_ContractModel):
    """一日一票目标权重。"""

    trading_date: date
    instrument_key: str
    weight: float
    leg: str = "LONG"  # LONG | SHORT | Qk
    factor_value: Optional[float] = None


class PortfolioReturnRow(_ContractModel):
    """理论组合日收益（gross）。"""

    trading_date: date
    portfolio_return: Optional[float] = None
    long_return: Optional[float] = None
    short_return: Optional[float] = None
    long_short_return: Optional[float] = None
    sample_count: int = 0


class PortfolioTurnoverRow(_ContractModel):
    trading_date: date
    turnover: Optional[float] = None
    rebalanced: bool = False


class PortfolioFrames(_ContractModel):
    portfolio_hash: str
    factor_dataset_id: str = ""
    evaluation_hash: str = ""
    positions: list[PortfolioPositionRow] = Field(default_factory=list)
    returns: list[PortfolioReturnRow] = Field(default_factory=list)
    turnover: list[PortfolioTurnoverRow] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioManifest(_ContractModel):
    portfolio_hash: str
    factor_dataset_id: str = ""
    evaluation_hash: str = ""
    portfolio_spec: dict[str, Any] = Field(default_factory=dict)
    position_rows: int = 0
    return_rows: int = 0
    checksum: str = ""
    portfolio_version: str = PORTFOLIO_VERSION
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "PORTFOLIO_VERSION",
    "ConstructionMethod",
    "Direction",
    "FactorPortfolioSummary",
    "PortfolioFrames",
    "PortfolioManifest",
    "PortfolioPositionRow",
    "PortfolioReturnRow",
    "PortfolioSpec",
    "PortfolioTurnoverRow",
    "RebalanceFrequency",
    "SelectionMode",
    "WeightMethod",
]
