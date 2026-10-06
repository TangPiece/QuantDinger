"""Phase 5E：Cross Validation Domain（不暴露 qlib / Production）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import Field, field_validator, model_validator

from app.services.research_data.contracts import CrossValidationSummary, _ContractModel
from app.services.research_data.research_backtest.protocol import (
    ResearchExecutionPolicy,
)

from .kinds import CvStatus, DiffKind

ENGINE_VERSION = "qd_cross_validation@1"

RealismMode = Literal["GROSS", "NET"]


class Tolerances(_ContractModel):
    """分层数值容差。"""

    signal_abs: float = 1e-8
    weight_abs: float = 1e-8
    nav_abs: float = 0.05
    nav_rel: float = 0.05
    perf_abs: float = 0.05
    other_abs: float = 1e-3


class CrossValidationSpec(_ContractModel):
    """交叉验证运行规格。"""

    strategy_hash: str
    start_date: date
    end_date: date
    backtest_hash: str = ""
    qlib_run_hash: str = ""
    execution_policy: ResearchExecutionPolicy = Field(
        default_factory=ResearchExecutionPolicy
    )
    realism: RealismMode = "GROSS"
    market_rule: str = "CN_A"
    initial_nav: float = 1.0
    cv_engine_version: str = ENGINE_VERSION
    tolerances: Tolerances = Field(default_factory=Tolerances)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("strategy_hash")
    @classmethod
    def _shash(cls, v: str) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("strategy_hash required")
        return s

    @model_validator(mode="after")
    def _window(self) -> "CrossValidationSpec":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        return self


class LayerResult(_ContractModel):
    """单层 Diff 结果。"""

    layer: str
    kind: DiffKind
    status: Literal["PASS", "FAIL", "SKIP"] = "PASS"
    message: str = ""
    max_abs_diff: Optional[float] = None
    max_rel_diff: Optional[float] = None
    first_divergence: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class AttributionBreakdown(_ContractModel):
    """收益差分层归因。"""

    data: float = 0.0
    signal: float = 0.0
    portfolio: float = 0.0
    execution: float = 0.0
    cost: float = 0.0
    other: float = 0.0
    total: float = 0.0
    notes: list[str] = Field(default_factory=list)


class CrossValidationReport(_ContractModel):
    """完整交叉验证报告。"""

    cv_hash: str
    strategy_hash: str
    backtest_hash: str = ""
    qlib_run_hash: str = ""
    start_date: str = ""
    end_date: str = ""
    realism: str = "GROSS"
    status: CvStatus = "FAILED"
    layers: list[LayerResult] = Field(default_factory=list)
    attribution: AttributionBreakdown = Field(default_factory=AttributionBreakdown)
    side_by_side: dict[str, Any] = Field(default_factory=dict)
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrossValidationManifest(_ContractModel):
    """CV 产物清单。"""

    cv_hash: str
    strategy_hash: str = ""
    engine_version: str = ENGINE_VERSION
    checksum: str = ""
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ENGINE_VERSION",
    "AttributionBreakdown",
    "CrossValidationManifest",
    "CrossValidationReport",
    "CrossValidationSpec",
    "CrossValidationSummary",
    "LayerResult",
    "Tolerances",
]
