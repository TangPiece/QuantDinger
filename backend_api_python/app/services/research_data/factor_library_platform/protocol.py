"""Phase 9E：Factor Library Platform 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_factor_library_platform@1"
LIBRARY_ENTRY_SCHEMA = "library_entry@1"
COLLECTION_SCHEMA = "factor_collection@1"
PORTFOLIO_SPEC_SCHEMA = "factor_portfolio_spec@1"
CLUSTER_SCHEMA = "factor_cluster@1"

LibraryLifecycle = Literal[
    "DRAFT",
    "CANDIDATE",
    "EVALUATING",
    "VALIDATED",
    "APPROVED",
    "ACTIVE",
    "DEPRECATED",
    "RETIRED",
]

FactorCategory = Literal[
    "MOMENTUM",
    "VALUE",
    "QUALITY",
    "VOLATILITY",
    "LIQUIDITY",
    "SENTIMENT",
    "TECHNICAL",
    "OTHER",
]

WeightMethod = Literal["EQUAL", "ICIR", "RISK", "CORR_ADJUSTED"]
ClusterMethod = Literal["threshold_components", "corr_threshold"]
PromotionVerdict = Literal["PASS", "REJECT"]


class _PlatformModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PromotionGateConfig(_PlatformModel):
    """晋升门阈值（可选）。"""

    min_quality_total: float = 0.0
    require_holdout_fields: bool = False
    record_complexity: bool = True
    record_redundancy: bool = True


class PromotionGateResult(_PlatformModel):
    verdict: PromotionVerdict
    reasons: list[str] = Field(default_factory=list)
    evaluation_id: str = ""
    factor_ref: str = ""
    quality_total: float = 0.0
    multiple_testing_warning: str = ""
    complexity_note: str = ""
    redundancy_note: str = ""


class FactorLibraryEntry(_PlatformModel):
    """图书馆索引条目（非 R2 因子值）。"""

    schema_version: str = LIBRARY_ENTRY_SCHEMA
    engine_version: str = ENGINE_VERSION
    entry_id: str
    factor_ref: str
    factor_hash: str
    evaluation_id: str
    dataset_ref: str = ""
    dataset_hash: str = ""
    lifecycle: LibraryLifecycle = "APPROVED"
    category: FactorCategory = "OTHER"
    tags: list[str] = Field(default_factory=list)
    quality_total: float = 0.0
    ic_score: float = 0.0
    icir_score: float = 0.0
    candidate_id: str = ""
    mining_run_id: str = ""
    multiple_testing_warning: str = ""
    replacement_ref: str = ""
    deprecate_reason: str = ""
    parent_factor_refs: list[str] = Field(default_factory=list)
    immutable: bool = True
    published_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorSearchQuery(_PlatformModel):
    """目录检索。"""

    lifecycle: list[LibraryLifecycle] = Field(default_factory=list)
    category: list[FactorCategory] = Field(default_factory=list)
    tags_any: list[str] = Field(default_factory=list)
    tags_all: list[str] = Field(default_factory=list)
    factor_ref_prefix: str = ""
    text: str = ""


class SimilarFactorHit(_PlatformModel):
    factor_ref: str
    corr: float
    source: str = "library_inject"


class FactorClusterPolicy(_PlatformModel):
    method: ClusterMethod = "threshold_components"
    corr_threshold: float = 0.85
    dataset_ref: str = ""
    dataset_hash: str = ""
    policy_version: str = "1.0.0"


class FactorCluster(_PlatformModel):
    schema_version: str = CLUSTER_SCHEMA
    engine_version: str = ENGINE_VERSION
    cluster_id: str
    cluster_hash: str
    method: ClusterMethod
    corr_threshold: float
    dataset_hash: str
    member_refs: list[str] = Field(default_factory=list)
    clusters: list[list[str]] = Field(default_factory=list)
    published_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorCollection(_PlatformModel):
    schema_version: str = COLLECTION_SCHEMA
    engine_version: str = ENGINE_VERSION
    collection_id: str
    name: str = ""
    version: str = "1.0.0"
    collection_hash: str
    member_refs: list[str] = Field(default_factory=list)
    immutable: bool = True
    published_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorPortfolioSpec(_PlatformModel):
    """组合定义（≠ 4I 执行 run）。"""

    schema_version: str = PORTFOLIO_SPEC_SCHEMA
    engine_version: str = ENGINE_VERSION
    portfolio_id: str
    name: str = ""
    version: str = "1.0.0"
    portfolio_spec_hash: str
    collection_id: str = ""
    member_refs: list[str] = Field(default_factory=list)
    weight_method: WeightMethod = "EQUAL"
    resolved_weights: dict[str, float] = Field(default_factory=dict)
    immutable: bool = True
    published_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorLibraryInject(_PlatformModel):
    """测试 / 编排注入。"""

    skip_immutability: bool = False
    gate_config: PromotionGateConfig = Field(default_factory=PromotionGateConfig)
    similarity_overrides: dict[str, list[SimilarFactorHit]] = Field(default_factory=dict)
    cluster_corr_matrix: dict[str, dict[str, float]] = Field(default_factory=dict)
    weight_metrics: dict[str, dict[str, float]] = Field(default_factory=dict)
    auto_activate: bool = False


__all__ = [
    "CLUSTER_SCHEMA",
    "COLLECTION_SCHEMA",
    "ENGINE_VERSION",
    "FactorCategory",
    "FactorCluster",
    "FactorClusterPolicy",
    "FactorCollection",
    "FactorLibraryEntry",
    "FactorLibraryInject",
    "FactorPortfolioSpec",
    "FactorSearchQuery",
    "LibraryLifecycle",
    "LIBRARY_ENTRY_SCHEMA",
    "PORTFOLIO_SPEC_SCHEMA",
    "PromotionGateConfig",
    "PromotionGateResult",
    "PromotionVerdict",
    "SimilarFactorHit",
    "WeightMethod",
]
