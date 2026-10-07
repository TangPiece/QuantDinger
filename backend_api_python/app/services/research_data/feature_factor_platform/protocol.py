"""Phase 9B：Feature / Factor Platform 契约（manifest / gate / 引擎版本）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_feature_factor_platform@1"
FEATURE_SET_MANIFEST_SCHEMA = "feature_set_manifest@1"
FACTOR_BUILD_INDEX_SCHEMA = "factor_build_index@1"


class _PlatformModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


QualityGateVerdict = Literal["PASS", "REJECT"]


class QualityGateResult(_PlatformModel):
    verdict: QualityGateVerdict = "PASS"
    reasons: list[str] = Field(default_factory=list)


class FeatureSetManifest(_PlatformModel):
    """FeatureSet 不可变 manifest（LocalJson + R2 镜像）。"""

    schema_version: str = FEATURE_SET_MANIFEST_SCHEMA
    engine_version: str = ENGINE_VERSION
    feature_set_code: str
    feature_set_version: str
    feature_set_hash: str
    name: str = ""
    member_refs: list[str] = Field(default_factory=list)
    processor: str = ""
    schema_version_ref: str = "feature_set@1"
    immutable: bool = True
    published_at: datetime
    r2_key: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorBuildIndex(_PlatformModel):
    """Factor 构建索引：钉住 9A dataset + factor_hash + 产物指针。"""

    schema_version: str = FACTOR_BUILD_INDEX_SCHEMA
    engine_version: str = ENGINE_VERSION
    factor_ref: str
    factor_hash: str
    dataset_ref: str
    dataset_hash: str
    snapshot_id: str
    layout: Literal["long", "wide"] = "long"
    start_date: str = ""
    end_date: str = ""
    factor_dataset_id: str = ""
    manifest_uri: str = ""
    parquet_index: list[dict[str, Any]] = Field(default_factory=list)
    immutable: bool = True
    published_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeatureSetBuildIndex(_PlatformModel):
    """FeatureSet 批量构建索引。"""

    schema_version: str = "feature_set_build_index@1"
    engine_version: str = ENGINE_VERSION
    feature_set_ref: str
    feature_set_hash: str
    dataset_ref: str
    dataset_hash: str
    snapshot_id: str
    layout: Literal["long", "wide"] = "long"
    start_date: str = ""
    end_date: str = ""
    member_builds: list[dict[str, Any]] = Field(default_factory=list)
    immutable: bool = True
    published_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorBuildResult(_PlatformModel):
    factor_ref: str
    factor_hash: str
    dataset_ref: str
    dataset_hash: str
    layout: Literal["long", "wide"]
    factor_dataset_id: str
    manifest_uri: str
    build_index_uri: str = ""


class FeatureBuildResult(_PlatformModel):
    feature_set_ref: str
    feature_set_hash: str
    dataset_ref: str
    dataset_hash: str
    layout: Literal["long", "wide"]
    member_builds: list[FactorBuildResult] = Field(default_factory=list)
    build_index_uri: str = ""


class LineageNode(_PlatformModel):
    ref: str
    kind: str
    hash_value: str = ""
    children: list["LineageNode"] = Field(default_factory=list)


LineageNode.model_rebuild()


class FeatureFactorBuildInject(_PlatformModel):
    """Fake golden 注入：gate / 不可变 / 计算元数据。"""

    gate_override: dict[str, Any] | None = None
    skip_immutability: bool = False
    skip_dataset_manifest_check: bool = False
    compute_metadata: dict[str, Any] | None = None


__all__ = [
    "ENGINE_VERSION",
    "FACTOR_BUILD_INDEX_SCHEMA",
    "FEATURE_SET_MANIFEST_SCHEMA",
    "FactorBuildIndex",
    "FactorBuildResult",
    "FeatureBuildResult",
    "FeatureFactorBuildInject",
    "FeatureSetBuildIndex",
    "FeatureSetManifest",
    "LineageNode",
    "QualityGateResult",
    "QualityGateVerdict",
]
