"""Phase 4E：Group Portfolio Evaluation Domain（非 Production Backtest）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import Field, field_validator, model_validator

from app.services.research_data.contracts import (
    GroupEvaluationSummary,
    _ContractModel,
)

GROUP_VERSION = "qd_factor_groups@1"
SCHEMA_MEMBERSHIP = "group_membership@1"
SCHEMA_RETURN = "group_return_daily@1"
SCHEMA_TURNOVER = "group_turnover_daily@1"

FactorDirection = Literal["POSITIVE", "NEGATIVE", "AUTO"]
PortfolioMode = Literal["LONG_ONLY", "LONG_SHORT", "BOTH"]
WeightingMethod = Literal["EQUAL_WEIGHT", "VALUE_WEIGHT", "CUSTOM_WEIGHT"]
CostKind = Literal["ZERO", "FIXED_BPS"]


class CostModelSpec(_ContractModel):
    """评价用估算成本（非撮合）。"""

    kind: CostKind = "ZERO"
    buy_cost_bps: float = 5.0
    sell_cost_bps: float = 10.0

    @field_validator("buy_cost_bps", "sell_cost_bps")
    @classmethod
    def _nonneg(cls, v: float) -> float:
        if float(v) < 0:
            raise ValueError("cost bps must be >= 0")
        return float(v)


class GroupSpec(_ContractModel):
    """分位组合评价规格。"""

    evaluation_hash: str
    group_count: Literal[2, 5, 10, 20] = 10
    weighting_method: WeightingMethod = "EQUAL_WEIGHT"
    direction: FactorDirection = "AUTO"
    portfolio_mode: PortfolioMode = "BOTH"
    horizons: Optional[list[int]] = None
    min_cross_section_size: int = 30
    allowed_sample_status: list[str] = Field(default_factory=lambda: ["VALID"])
    cost_model: CostModelSpec = Field(default_factory=CostModelSpec)
    group_version: str = GROUP_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("min_cross_section_size")
    @classmethod
    def _min_cs(cls, v: int) -> int:
        if int(v) < 2:
            raise ValueError("min_cross_section_size must be >= 2")
        return int(v)

    @model_validator(mode="after")
    def _weighting(self) -> "GroupSpec":
        if self.weighting_method != "EQUAL_WEIGHT":
            raise ValueError(
                f"weighting_method={self.weighting_method!r} not implemented in 4E; "
                "only EQUAL_WEIGHT"
            )
        return self


class MembershipRow(_ContractModel):
    evaluation_date: date
    horizon: int
    instrument_key: str
    factor_value: float
    factor_rank: float
    group: int
    weight: float


class GroupReturnRow(_ContractModel):
    evaluation_date: date
    horizon: int
    group: int
    group_return: Optional[float] = None
    sample_count: int = 0
    long_return: Optional[float] = None
    short_return: Optional[float] = None
    long_short_return: Optional[float] = None
    estimated_cost: Optional[float] = None
    net_long_short_return: Optional[float] = None


class TurnoverRow(_ContractModel):
    evaluation_date: date
    horizon: int
    portfolio: str
    turnover: Optional[float] = None  # 首日 NaN
    previous_weight_count: int = 0
    current_weight_count: int = 0


class GroupFrames(_ContractModel):
    """内存评价帧。"""

    group_evaluation_hash: str
    evaluation_hash: str
    horizons: list[int] = Field(default_factory=list)
    membership: list[MembershipRow] = Field(default_factory=list)
    returns: list[GroupReturnRow] = Field(default_factory=list)
    turnover: list[TurnoverRow] = Field(default_factory=list)
    direction: Literal["POSITIVE", "NEGATIVE"] = "POSITIVE"
    metadata: dict[str, Any] = Field(default_factory=dict)


class GroupManifest(_ContractModel):
    group_evaluation_hash: str
    evaluation_hash: str
    factor_dataset_id: str = ""
    group_spec: dict[str, Any] = Field(default_factory=dict)
    horizons: list[int] = Field(default_factory=list)
    membership_rows: int = 0
    return_rows: int = 0
    turnover_rows: int = 0
    checksum: str = ""
    group_version: str = GROUP_VERSION
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "GROUP_VERSION",
    "CostModelSpec",
    "FactorDirection",
    "GroupEvaluationSummary",
    "GroupFrames",
    "GroupManifest",
    "GroupReturnRow",
    "GroupSpec",
    "MembershipRow",
    "PortfolioMode",
    "TurnoverRow",
]
