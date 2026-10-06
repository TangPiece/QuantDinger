"""Phase 4D：IC / RankIC Metric Domain 契约（无 Forward Return 重算）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import Field, field_validator

from app.services.research_data.contracts import (
    FactorEvaluationSummary,
    _ContractModel,
)

METRIC_VERSION = "qd_factor_metrics@1"
CALCULATOR_VERSION = "qd_cs_corr@1"
SCHEMA_METRIC_IC = "metric_ic_daily@1"

FactorDirection = Literal["AUTO", "POSITIVE", "NEGATIVE"]


class MetricSpec(_ContractModel):
    """横截面指标规格；只消费 4C Evaluation Dataset。"""

    evaluation_hash: str
    horizons: Optional[list[int]] = None
    min_cross_section_size: int = 30
    allowed_sample_status: list[str] = Field(default_factory=lambda: ["VALID"])
    direction: FactorDirection = "AUTO"
    metric_version: str = METRIC_VERSION
    calculator_version: str = CALCULATOR_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("min_cross_section_size")
    @classmethod
    def _min_size(cls, v: int) -> int:
        if int(v) < 2:
            raise ValueError("min_cross_section_size must be >= 2")
        return int(v)

    @field_validator("horizons")
    @classmethod
    def _horizons(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        if v is None:
            return None
        out = sorted({int(h) for h in v})
        if any(h <= 0 for h in out):
            raise ValueError("horizons must be positive")
        return out


class MetricPoint(_ContractModel):
    """单日 × 单 horizon 的 IC / RankIC。"""

    evaluation_date: date
    horizon: int
    ic: Optional[float] = None
    rank_ic: Optional[float] = None
    sample_count: int = 0
    valid: bool = False


class MetricTimeSeries(_ContractModel):
    """IC / RankIC 时间序列一级产物。"""

    metric_hash: str
    evaluation_hash: str
    horizons: list[int] = Field(default_factory=list)
    points: list[MetricPoint] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def row_count(self) -> int:
        return len(self.points)


class MetricManifest(_ContractModel):
    """R2 metrics manifest。"""

    metric_hash: str
    evaluation_hash: str
    factor_dataset_id: str = ""
    metric_spec: dict[str, Any] = Field(default_factory=dict)
    horizons: list[int] = Field(default_factory=list)
    row_count: int = 0
    min_date: str = ""
    max_date: str = ""
    checksum: str = ""
    metric_version: str = METRIC_VERSION
    calculator_version: str = CALCULATOR_VERSION
    schema_version: str = SCHEMA_METRIC_IC
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


def point_date_str(d: date | datetime | str) -> str:
    """统一日期字符串。"""
    if isinstance(d, datetime):
        return d.date().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    return str(d)[:10]


# 再导出 Summary，便于 metrics 包统一导入
__all__ = [
    "CALCULATOR_VERSION",
    "METRIC_VERSION",
    "SCHEMA_METRIC_IC",
    "FactorDirection",
    "FactorEvaluationSummary",
    "MetricManifest",
    "MetricPoint",
    "MetricSpec",
    "MetricTimeSeries",
    "point_date_str",
]
