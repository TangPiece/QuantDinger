"""Factor Lab Domain 视图（研究侧；非交易 services.factors）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from app.services.research_data.contracts import (
    FeatureDefinition,
    FactorDatasetRecord,
    PricePolicy,
    _ContractModel,
)

from .hash import compute_factor_hash
from .types import SCHEMA_LONG


class FactorDependency(_ContractModel):
    """单条因子依赖。"""

    dependency_type: str
    dependency_code: str


class FactorSpec(_ContractModel):
    """Research Factor 视图：基于 FeatureDefinition，便于 Lab API。"""

    code: str
    version: str
    name: str
    expression: str
    description: str = ""
    factor_type: str = "CUSTOM"
    computation_engine: str = "quantdinger"
    engine_version: str = ""
    frequency: str = "1d"
    universe: Optional[str] = None
    information_policy: str = "UNKNOWN"
    schema_version: str = SCHEMA_LONG
    backend: str = "r2_factor"
    online_supported: bool = False
    dependencies: list[str] = Field(default_factory=list)
    factor_hash: Optional[str] = None
    price_policy: Optional[PricePolicy] = None
    processor_ref: Optional[str] = None
    definition: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_feature(cls, feature: FeatureDefinition) -> "FactorSpec":
        """FeatureDefinition → FactorSpec。"""
        return cls.model_validate(feature.model_dump(mode="json"))

    def to_feature(self) -> FeatureDefinition:
        """FactorSpec → FeatureDefinition（注册前可补 hash）。"""
        feat = FeatureDefinition.model_validate(self.model_dump(mode="json"))
        if not feat.factor_hash:
            feat = feat.model_copy(update={"factor_hash": compute_factor_hash(feat)})
        return feat

    @property
    def factor_ref(self) -> str:
        return f"{self.code}@{self.version}"


class FactorDatasetManifest(_ContractModel):
    """R2 Factor Dataset Manifest 契约。"""

    factor_code: str
    factor_version: str
    factor_hash: str
    dataset_hash: str
    snapshot_id: str
    schema_version: str
    min_date: str
    max_date: str
    universe: str = ""
    row_count: int = 0
    checksum: str = ""
    layout: Literal["long", "wide"] = "long"
    engine: str = ""
    engine_version: str = ""
    factor_dataset_id: str = ""
    frequency: str = "1d"
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# 再导出，便于外部统一导入
__all__ = [
    "FactorDependency",
    "FactorDatasetManifest",
    "FactorDatasetRecord",
    "FactorSpec",
]
