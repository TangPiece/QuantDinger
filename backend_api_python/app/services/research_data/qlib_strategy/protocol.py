"""Phase 5D：Qlib Strategy Adapter Domain（不暴露 qlib.strategy.*）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import Field, field_validator, model_validator

from app.services.research_data.contracts import QlibRunSummary, _ContractModel
from app.services.research_data.research_backtest.protocol import (
    ResearchExecutionPolicy,
)

ENGINE_VERSION = "qlib_strategy_adapter@1"

RealismMode = Literal["GROSS", "NET"]
MarketRuleId = Literal["CN_A", "HK", "US"]
CompatibilityLevel = Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED"]


class CompatibilityItem(_ContractModel):
    """单项执行/策略能力兼容性。"""

    capability: str
    level: CompatibilityLevel
    note: str = ""


class CompatibilityReport(_ContractModel):
    """ExecutionCompatibility 汇总（写入 Summary）。"""

    realism: RealismMode = "GROSS"
    market_rule: str = "CN_A"
    items: list[CompatibilityItem] = Field(default_factory=list)
    has_unsupported: bool = False
    has_partial: bool = False


class StrategyPlan(_ContractModel):
    """Portfolio → Qlib 策略计划声明（v1 仅 WeightStrategy）。"""

    strategy_kind: str = "WEIGHT_FROM_TARGET_POSITION"
    weight_method: str = "FROM_TARGET_POSITION"
    rebalance_note: str = "HOLD_UNTIL_NEXT_REBALANCE"
    native_topk_enabled: bool = False


class QlibStrategySpec(_ContractModel):
    """Qlib 策略适配运行规格。"""

    strategy_hash: str
    start_date: date
    end_date: date
    execution_policy: ResearchExecutionPolicy = Field(
        default_factory=ResearchExecutionPolicy
    )
    realism: RealismMode = "GROSS"
    market_rule: MarketRuleId = "CN_A"
    initial_nav: float = 1.0
    dataset_ref: str = ""
    materialization_id: str = ""
    dataset_hash: str = ""
    qlib_engine_version: str = ENGINE_VERSION
    region: str = "cn"
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
    def _window(self) -> "QlibStrategySpec":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        return self


class QlibRunManifest(_ContractModel):
    """Qlib run 产物清单。"""

    qlib_run_hash: str
    strategy_hash: str = ""
    materialization_id: str = ""
    engine_version: str = ENGINE_VERSION
    checksum: str = ""
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ENGINE_VERSION",
    "CompatibilityItem",
    "CompatibilityLevel",
    "CompatibilityReport",
    "QlibRunManifest",
    "QlibRunSummary",
    "QlibStrategySpec",
    "StrategyPlan",
]
