"""Phase 4F：Factor Stability / Decay Domain 契约（非 Production Backtest）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import Field, field_validator, model_validator

from app.services.research_data.contracts import (
    FactorStabilitySummary,
    _ContractModel,
)
from app.services.research_data.factor_lab.groups.protocol import (
    CostModelSpec,
    PortfolioMode,
)
from app.services.research_data.factor_lab.metrics.protocol import MetricPoint

STABILITY_VERSION = "qd_factor_stability@1"
SCHEMA_ROLLING_IC = "rolling_ic_daily@1"
SCHEMA_DECAY = "decay_curve@1"
SCHEMA_GROUP_STABILITY = "group_stability_daily@1"
SCHEMA_REGIME = "regime_metrics@1"

DEFAULT_ROLLING_WINDOWS = [20, 60, 120, 252]
DEFAULT_DECAY_HORIZONS = [1, 2, 3, 5, 10, 20]

FactorDirection = Literal["POSITIVE", "NEGATIVE", "AUTO"]
RegimeType = Literal["YEAR", "QUARTER"]
GroupCount = Literal[2, 5, 10, 20]


class StabilitySpec(_ContractModel):
    """稳定性评价规格；只消费 4C Evaluation Dataset。"""

    evaluation_hash: str
    rolling_windows: list[int] = Field(
        default_factory=lambda: list(DEFAULT_ROLLING_WINDOWS)
    )
    decay_horizons: Optional[list[int]] = None
    regime_types: list[RegimeType] = Field(
        default_factory=lambda: ["YEAR", "QUARTER"]
    )
    min_cross_section_size: int = 30
    min_rolling_samples: int = 10
    allowed_sample_status: list[str] = Field(default_factory=lambda: ["VALID"])
    direction: FactorDirection = "AUTO"
    group_count: GroupCount = 10
    portfolio_mode: PortfolioMode = "BOTH"
    cost_model: CostModelSpec = Field(default_factory=CostModelSpec)
    stability_version: str = STABILITY_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("min_cross_section_size")
    @classmethod
    def _min_cs(cls, v: int) -> int:
        if int(v) < 2:
            raise ValueError("min_cross_section_size must be >= 2")
        return int(v)

    @field_validator("min_rolling_samples")
    @classmethod
    def _min_roll(cls, v: int) -> int:
        if int(v) < 1:
            raise ValueError("min_rolling_samples must be >= 1")
        return int(v)

    @field_validator("rolling_windows")
    @classmethod
    def _windows(cls, v: list[int]) -> list[int]:
        out = sorted({int(x) for x in v})
        if not out or any(x <= 0 for x in out):
            raise ValueError("rolling_windows must be positive ints")
        return out

    @field_validator("decay_horizons")
    @classmethod
    def _decay_h(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        if v is None:
            return None
        out = sorted({int(h) for h in v})
        if any(h <= 0 for h in out):
            raise ValueError("decay_horizons must be positive")
        return out

    @model_validator(mode="after")
    def _regime(self) -> "StabilitySpec":
        allowed = {"YEAR", "QUARTER"}
        for t in self.regime_types:
            if t not in allowed:
                raise ValueError(
                    f"regime_type={t!r} not supported in 4F; only YEAR/QUARTER"
                )
        if not self.regime_types:
            raise ValueError("regime_types must be non-empty")
        return self


class RollingICRow(_ContractModel):
    """单日 × horizon × window 的滚动 IC。"""

    evaluation_date: date
    horizon: int
    window: int
    ic_mean: Optional[float] = None
    rankic_mean: Optional[float] = None
    ic_std: Optional[float] = None
    ic_positive_ratio: Optional[float] = None
    sample_count: int = 0


class ICDistribution(_ContractModel):
    """IC 或 RankIC 全样本分布。"""

    metric: Literal["IC", "RANK_IC"]
    horizon: int
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    p05: Optional[float] = None
    p25: Optional[float] = None
    p50: Optional[float] = None
    p75: Optional[float] = None
    p95: Optional[float] = None
    positive_ratio: Optional[float] = None
    negative_ratio: Optional[float] = None
    sample_count: int = 0


class DecayPoint(_ContractModel):
    """单 horizon 的 Decay 观测点（无拟合）。"""

    horizon: int
    ic_mean: Optional[float] = None
    rankic_mean: Optional[float] = None
    long_return: Optional[float] = None
    short_return: Optional[float] = None
    long_short_return: Optional[float] = None
    sample_count: int = 0


class GroupStabilityRow(_ContractModel):
    """Group / LS 滚动稳定性日频行。"""

    evaluation_date: date
    horizon: int
    window: int
    portfolio: str  # TOP / BOTTOM / LONG / SHORT / LONG_SHORT
    mean_return: Optional[float] = None
    std_return: Optional[float] = None
    positive_ratio: Optional[float] = None
    sample_count: int = 0


class RegimeRow(_ContractModel):
    """日历 Regime 聚合行。"""

    regime_type: RegimeType
    regime_value: str
    horizon: int
    ic_mean: Optional[float] = None
    rankic_mean: Optional[float] = None
    long_short_return: Optional[float] = None
    turnover: Optional[float] = None
    net_return: Optional[float] = None
    sample_count: int = 0


class StabilityFrames(_ContractModel):
    """内存稳定性帧。"""

    stability_hash: str
    evaluation_hash: str
    horizons: list[int] = Field(default_factory=list)
    rolling_ic: list[RollingICRow] = Field(default_factory=list)
    distributions: list[ICDistribution] = Field(default_factory=list)
    decay: list[DecayPoint] = Field(default_factory=list)
    group_stability: list[GroupStabilityRow] = Field(default_factory=list)
    regime: list[RegimeRow] = Field(default_factory=list)
    metric_points: list[MetricPoint] = Field(default_factory=list)
    direction: Literal["POSITIVE", "NEGATIVE"] = "POSITIVE"
    metadata: dict[str, Any] = Field(default_factory=dict)


class StabilityManifest(_ContractModel):
    stability_hash: str
    evaluation_hash: str
    factor_dataset_id: str = ""
    stability_spec: dict[str, Any] = Field(default_factory=dict)
    horizons: list[int] = Field(default_factory=list)
    rolling_rows: int = 0
    decay_rows: int = 0
    group_stability_rows: int = 0
    regime_rows: int = 0
    checksum: str = ""
    stability_version: str = STABILITY_VERSION
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "DEFAULT_DECAY_HORIZONS",
    "DEFAULT_ROLLING_WINDOWS",
    "SCHEMA_DECAY",
    "SCHEMA_GROUP_STABILITY",
    "SCHEMA_REGIME",
    "SCHEMA_ROLLING_IC",
    "STABILITY_VERSION",
    "CostModelSpec",
    "DecayPoint",
    "FactorDirection",
    "FactorStabilitySummary",
    "GroupStabilityRow",
    "ICDistribution",
    "MetricPoint",
    "RegimeRow",
    "RegimeType",
    "RollingICRow",
    "StabilityFrames",
    "StabilityManifest",
    "StabilitySpec",
]
