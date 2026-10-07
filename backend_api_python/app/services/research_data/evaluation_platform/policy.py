"""EvaluationPolicy：统一 IC / 分层 / 稳定性参数。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from app.services.research_data.contracts import PricePolicy, _ContractModel
from app.services.research_data.factor_lab.evaluation.protocol import (
    EvaluationMode,
    ReturnSpec,
)
from app.services.research_data.factor_lab.groups.protocol import CostModelSpec
from app.services.research_data.factor_lab.stability.protocol import (
    DEFAULT_DECAY_HORIZONS,
    DEFAULT_ROLLING_WINDOWS,
)

FactorDirection = Literal["AUTO", "POSITIVE", "NEGATIVE"]


class EvaluationPolicy(_ContractModel):
    """可版本化评价政策；content hash 参与 run 幂等键。"""

    policy_id: str
    version: str = "1.0.0"
    name: str = ""
    return_spec: ReturnSpec = Field(default_factory=ReturnSpec)
    price_policy: PricePolicy = Field(default_factory=PricePolicy)
    mode: EvaluationMode = "CROSS_SECTIONAL"
    exchange: str = "CN"
    ic_direction: FactorDirection = "AUTO"
    min_cross_section_size: int = 30
    quantile_count: Literal[2, 5, 10, 20] = 10
    cost_model: CostModelSpec = Field(default_factory=CostModelSpec)
    rolling_windows: list[int] = Field(
        default_factory=lambda: list(DEFAULT_ROLLING_WINDOWS)
    )
    decay_horizons: list[int] | None = None
    regime_types: list[Literal["YEAR", "QUARTER"]] = Field(
        default_factory=lambda: ["YEAR", "QUARTER"]
    )
    annualization_trading_days: int = 252
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("min_cross_section_size")
    @classmethod
    def _min_cs(cls, v: int) -> int:
        if int(v) < 2:
            raise ValueError("min_cross_section_size must be >= 2")
        return int(v)

    @field_validator("rolling_windows")
    @classmethod
    def _windows(cls, v: list[int]) -> list[int]:
        out = sorted({int(x) for x in v})
        if not out or any(x <= 0 for x in out):
            raise ValueError("rolling_windows must be positive")
        return out

    def canonical_payload(self) -> dict[str, Any]:
        decay = self.decay_horizons if self.decay_horizons is not None else list(
            DEFAULT_DECAY_HORIZONS
        )
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "return_spec": self.return_spec.model_dump(mode="json"),
            "price_policy": self.price_policy.model_dump(mode="json"),
            "mode": self.mode,
            "exchange": self.exchange,
            "ic_direction": self.ic_direction,
            "min_cross_section_size": self.min_cross_section_size,
            "quantile_count": self.quantile_count,
            "cost_model": self.cost_model.model_dump(mode="json"),
            "rolling_windows": list(self.rolling_windows),
            "decay_horizons": decay,
            "regime_types": list(self.regime_types),
            "annualization_trading_days": int(self.annualization_trading_days),
        }


__all__ = ["EvaluationPolicy", "FactorDirection"]
