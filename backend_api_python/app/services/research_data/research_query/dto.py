"""UI-facing read DTOs (not raw domain dumps)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Dto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PeriodDto(_Dto):
    start: str = ""
    end: str = ""


class EvaluationSeriesDto(_Dto):
    dates: list[str] = Field(default_factory=list)
    ic: list[float | None] = Field(default_factory=list)
    rank_ic: list[float | None] = Field(default_factory=list)


class DatasetListItemDto(_Dto):
    dataset_id: str
    name: str
    version: str
    dataset_hash: str
    universe: str
    frequency: str
    status: str = "READY"
    feature_count: int = 0
    label_count: int = 0
    period: PeriodDto = Field(default_factory=PeriodDto)
    feature_set: str = ""
    label_name: str = ""
    pit_policy: str = "STRICT"


class DatasetDetailDto(DatasetListItemDto):
    price_policy: str = "RAW"
    snapshot_id: str = ""
    processor: str = ""
    schema_features: list[dict[str, str]] = Field(default_factory=list)
    quality_checks: list[dict[str, str]] = Field(default_factory=list)
    lineage: list[dict[str, str]] = Field(default_factory=list)
    materialization: dict[str, Any] = Field(default_factory=dict)
    preview_available: bool = False
    preview_rows: list[dict[str, Any]] = Field(default_factory=list)


class FeatureListItemDto(_Dto):
    feature_id: str
    name: str
    version: str
    factor_hash: str = ""
    factor_type: str = ""
    expression: str = ""
    frequency: str = "1d"


class FeatureDetailDto(FeatureListItemDto):
    dependencies: list[str] = Field(default_factory=list)
    backend: str = ""
    description: str = ""


class AlphaFactorListItemDto(_Dto):
    factor_id: str
    name: str
    version: str
    factor_hash: str = ""
    expression: str = ""
    factor_type: str = ""
    lifecycle: str = ""
    icir: float | None = None
    turnover: float | None = None


class AlphaFactorDetailDto(AlphaFactorListItemDto):
    dependencies: list[str] = Field(default_factory=list)
    backend: str = ""
    description: str = ""
    frequency: str = "1d"


class AlphaFactorEvaluationDto(_Dto):
    factor_id: str
    factor_hash: str = ""
    has_result: bool = False
    horizon: int = 0
    mean_ic: float | None = None
    mean_rank_ic: float | None = None
    ic_ir: float | None = None
    rank_ic_ir: float | None = None
    turnover: float | None = None
    evaluation_hash: str = ""
    metric_hash: str = ""
    source_ref: str = ""
    series: EvaluationSeriesDto = Field(default_factory=EvaluationSeriesDto)
    # Back-compat aliases for early UI
    ic: float | None = None
    rank_ic: float | None = None
    icir: float | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class FactorLibraryItemDto(_Dto):
    entry_id: str
    factor_ref: str
    category: str = ""
    status: str = ""
    evaluation_id: str = ""


class FactorPortfolioItemDto(_Dto):
    portfolio_id: str
    name: str = ""
    factor_count: int = 0
    status: str = ""


class ModelListItemDto(_Dto):
    model_id: str
    model_code: str
    name: str = ""
    active_version: str = ""
    lifecycle: str = ""


class ModelDetailDto(_Dto):
    model_version_id: str
    model_id: str = ""
    model_code: str
    version: str
    name: str = ""
    model_type: str = ""
    framework: str = ""
    lifecycle: str = ""
    dataset_ref: str = ""
    feature_set_id: str = ""
    factor_portfolio_id: str = ""
    label_id: str = ""
    processor_version: str = ""
    training_run_id: str = ""
    artifact_id: str = ""
    status_summary: str = ""
    note: str = "Model ACTIVE is not Strategy LIVE"


class ArtifactDetailDto(_Dto):
    artifact_id: str
    kind: str = ""
    uri: str = ""
    checksum: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductStatusDto(_Dto):
    research: dict[str, str] = Field(default_factory=dict)
    strategy: dict[str, int] = Field(default_factory=dict)
    models_active: int = 0
    strategies_live: int = 0
    jobs: list[dict[str, str]] = Field(default_factory=list)


class ExperimentListItemDto(_Dto):
    experiment_id: str
    name: str
    dataset_ref: str
    status: Literal["COMPLETED", "FAILED"] = "COMPLETED"
    model_version_ref: str = ""


class ExperimentDetailDto(ExperimentListItemDto):
    snapshot_id: str = ""
    dataset_hash: str = ""
    feature_refs: list[str] = Field(default_factory=list)
    processor_ref: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    manifest_uri: str = ""


__all__ = [
    "AlphaFactorDetailDto",
    "AlphaFactorEvaluationDto",
    "AlphaFactorListItemDto",
    "ArtifactDetailDto",
    "DatasetDetailDto",
    "DatasetListItemDto",
    "EvaluationSeriesDto",
    "ExperimentDetailDto",
    "ExperimentListItemDto",
    "FactorLibraryItemDto",
    "FactorPortfolioItemDto",
    "FeatureDetailDto",
    "FeatureListItemDto",
    "ModelDetailDto",
    "ModelListItemDto",
    "PeriodDto",
    "ProductStatusDto",
]
