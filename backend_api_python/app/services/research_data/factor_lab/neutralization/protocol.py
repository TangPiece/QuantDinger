"""Phase 4G：Factor Neutralization Domain（Factor Transformation，非 Evaluation Engine）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import Field, field_validator, model_validator

from app.services.research_data.contracts import (
    FactorNeutralizationSummary,
    _ContractModel,
)

NEUTRALIZATION_VERSION = "qd_factor_neutralization@1"
SCHEMA_NEUTRALIZED = "neutralized_factor_daily@1"
SCHEMA_EXPOSURE = "exposure_daily@1"
SCHEMA_DIAGNOSTICS = "neutralization_diagnostics@1"

NeutralizationMethod = Literal["REGRESSION"]
NeutralizationTarget = Literal["SIZE", "BETA", "INDUSTRY"]
SizeTransform = Literal["LOG", "RAW"]
Strength = Literal["FULL", "PARTIAL"]
DayStatus = Literal["OK", "INSUFFICIENT", "SINGULAR", "CONSTANT", "MISSING"]


class NeutralizationSpec(_ContractModel):
    """中性化规格；只读源 Factor Dataset，不覆盖 Raw。"""

    factor_dataset_id: str
    method: NeutralizationMethod = "REGRESSION"
    targets: list[NeutralizationTarget] = Field(
        default_factory=lambda: ["SIZE", "INDUSTRY"]
    )
    size_metric_code: str = "MARKET_CAP"
    size_transform: SizeTransform = "LOG"
    industry_version: str = "injected@1"
    industry_panel_uri: str = ""
    include_intercept: bool = True
    min_cross_section_size: int = 30
    strength: Strength = "FULL"
    neutralization_version: str = NEUTRALIZATION_VERSION
    exposure_dataset_versions: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("min_cross_section_size")
    @classmethod
    def _min_cs(cls, v: int) -> int:
        if int(v) < 2:
            raise ValueError("min_cross_section_size must be >= 2")
        return int(v)

    @model_validator(mode="after")
    def _validate(self) -> "NeutralizationSpec":
        if self.method != "REGRESSION":
            raise ValueError(f"method={self.method!r} not implemented in 4G v1")
        if self.strength != "FULL":
            raise ValueError("strength=PARTIAL not implemented in 4G v1; only FULL")
        if not self.targets:
            raise ValueError("targets must be non-empty")
        # 去重保序
        seen: list[str] = []
        for t in self.targets:
            if t not in seen:
                seen.append(t)
        object.__setattr__(self, "targets", seen)
        return self


class ExposureRow(_ContractModel):
    """单日单票暴露。"""

    instrument_key: str
    trading_date: date
    exposure_code: str
    exposure_value: float
    available_time: Optional[datetime] = None


class NeutralizedFactorRow(_ContractModel):
    """审计用：raw + neutralized。"""

    instrument_key: str
    trading_date: date
    raw_factor: float
    neutralized_factor: Optional[float] = None
    status: DayStatus = "OK"


class ExposureDiagnostic(_ContractModel):
    """按日 × exposure 的 before/after 诊断。"""

    trading_date: date
    exposure_code: str
    correlation_before: Optional[float] = None
    correlation_after: Optional[float] = None
    spearman_before: Optional[float] = None
    spearman_after: Optional[float] = None
    r_squared: Optional[float] = None
    sample_count: int = 0
    status: DayStatus = "OK"


class NeutralizationFrames(_ContractModel):
    """内存帧。"""

    neutralization_hash: str
    factor_dataset_id: str
    factor_rows: list[NeutralizedFactorRow] = Field(default_factory=list)
    exposure_rows: list[ExposureRow] = Field(default_factory=list)
    diagnostics: list[ExposureDiagnostic] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NeutralizationManifest(_ContractModel):
    neutralization_hash: str
    factor_dataset_id: str
    factor_dataset_hash: str = ""
    neutralized_factor_dataset_id: str = ""
    neut_factor_ref: str = ""
    neutralization_spec: dict[str, Any] = Field(default_factory=dict)
    factor_rows: int = 0
    exposure_rows: int = 0
    diagnostic_rows: int = 0
    checksum: str = ""
    neutralization_version: str = NEUTRALIZATION_VERSION
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "NEUTRALIZATION_VERSION",
    "SCHEMA_DIAGNOSTICS",
    "SCHEMA_EXPOSURE",
    "SCHEMA_NEUTRALIZED",
    "DayStatus",
    "ExposureDiagnostic",
    "ExposureRow",
    "FactorNeutralizationSummary",
    "NeutralizationFrames",
    "NeutralizationManifest",
    "NeutralizationMethod",
    "NeutralizationSpec",
    "NeutralizationTarget",
    "NeutralizedFactorRow",
    "SizeTransform",
    "Strength",
]
