"""Phase 4H：Factor Combination Domain（Factor Transformation，非 Portfolio）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import Field, field_validator, model_validator

from app.services.research_data.contracts import (
    FactorCombinationSummary,
    _ContractModel,
)

COMBINATION_VERSION = "qd_factor_combination@1"
SCHEMA_COMPOSITE = "composite_factor_daily@1"
SCHEMA_CORR = "factor_corr_matrix@1"
SCHEMA_WEIGHTS = "combination_weights@1"

NormalizeMethod = Literal["RANK", "ZSCORE"]
WeightMethod = Literal["EQUAL", "IC_WEIGHT", "CORR_ADJUSTED", "ORTHOGONALIZE"]
MissingPolicy = Literal["DROP_ROW"]


class CombinationSpec(_ContractModel):
    """多因子组合规格；只读成员 Factor Dataset。"""

    member_factor_dataset_ids: list[str]
    normalize: NormalizeMethod = "RANK"
    weight_method: WeightMethod = "EQUAL"
    member_ic: dict[str, float] = Field(default_factory=dict)
    redundancy_corr_threshold: float = 0.7
    min_cross_section_size: int = 30
    missing_policy: MissingPolicy = "DROP_ROW"
    combination_version: str = COMBINATION_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("min_cross_section_size")
    @classmethod
    def _min_cs(cls, v: int) -> int:
        if int(v) < 2:
            raise ValueError("min_cross_section_size must be >= 2")
        return int(v)

    @field_validator("redundancy_corr_threshold")
    @classmethod
    def _thr(cls, v: float) -> float:
        f = float(v)
        if not (0.0 < f <= 1.0):
            raise ValueError("redundancy_corr_threshold must be in (0, 1]")
        return f

    @model_validator(mode="after")
    def _validate(self) -> "CombinationSpec":
        if self.missing_policy != "DROP_ROW":
            raise ValueError("missing_policy only DROP_ROW in 4H v1")
        seen: list[str] = []
        for mid in self.member_factor_dataset_ids:
            if mid not in seen:
                seen.append(str(mid))
        if len(seen) < 2:
            raise ValueError("member_factor_dataset_ids must have >= 2 unique ids")
        object.__setattr__(self, "member_factor_dataset_ids", seen)
        return self


class AlignedRow(_ContractModel):
    """对齐后的一日一票多因子值（原始）。"""

    trading_date: date
    instrument_key: str
    values: dict[str, float] = Field(default_factory=dict)  # id -> raw


class NormalizedRow(_ContractModel):
    """标准化后的一日一票。"""

    trading_date: date
    instrument_key: str
    values: dict[str, float] = Field(default_factory=dict)


class CorrCell(_ContractModel):
    factor_i: str
    factor_j: str
    corr: float


class RedundancyPair(_ContractModel):
    factor_i: str
    factor_j: str
    corr: float


class WeightEntry(_ContractModel):
    factor_dataset_id: str
    weight: float


class CompositeRow(_ContractModel):
    trading_date: date
    instrument_key: str
    composite: float
    member_values: dict[str, float] = Field(default_factory=dict)


class CombinationFrames(_ContractModel):
    combination_hash: str
    member_ids: list[str] = Field(default_factory=list)
    composite_rows: list[CompositeRow] = Field(default_factory=list)
    corr_cells: list[CorrCell] = Field(default_factory=list)
    redundancy_pairs: list[RedundancyPair] = Field(default_factory=list)
    weights: list[WeightEntry] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CombinationManifest(_ContractModel):
    combination_hash: str
    member_factor_dataset_ids: list[str] = Field(default_factory=list)
    composite_factor_dataset_id: str = ""
    composite_factor_ref: str = ""
    combination_spec: dict[str, Any] = Field(default_factory=dict)
    composite_rows: int = 0
    checksum: str = ""
    combination_version: str = COMBINATION_VERSION
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "COMBINATION_VERSION",
    "AlignedRow",
    "CombinationFrames",
    "CombinationManifest",
    "CombinationSpec",
    "CompositeRow",
    "CorrCell",
    "FactorCombinationSummary",
    "MissingPolicy",
    "NormalizeMethod",
    "NormalizedRow",
    "RedundancyPair",
    "WeightEntry",
    "WeightMethod",
]
