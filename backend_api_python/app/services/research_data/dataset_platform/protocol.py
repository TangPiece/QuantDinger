"""Phase 9A：Research Dataset Platform 契约（manifest / gate / 引擎版本）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.services.research_data.contracts import DatasetDefinition, LabelDefinition, PricePolicy

ENGINE_VERSION = "qd_dataset_platform@1"
MANIFEST_SCHEMA_VERSION = "dataset_manifest@1"


class _PlatformModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DatasetLineageItem(_PlatformModel):
    """Snapshot 条目摘要（checksum 用于 gate / manifest）。"""

    dataset_code: str
    version: str
    path: str = ""
    checksum: str = ""
    r2_uri: str = ""


class DatasetManifest(_PlatformModel):
    """不可变 Dataset 包 manifest（R2 / 本地镜像）。"""

    schema_version: str = MANIFEST_SCHEMA_VERSION
    engine_version: str = ENGINE_VERSION
    dataset_code: str
    dataset_version: str
    snapshot_id: str
    dataset_hash: str
    name: str = ""
    frequency: str = "1d"
    universe_code: str = ""
    universe_version: str = ""
    schema_version_ref: str = Field(
        default="",
        description="DatasetDefinition.schema_version（字段名避免与 manifest schema_version 冲突）",
    )
    features: list[str] = Field(default_factory=list)
    label: Optional[LabelDefinition] = None
    processor: str = ""
    price_policy: PricePolicy = Field(default_factory=PricePolicy)
    pit: bool = True
    lineage: list[DatasetLineageItem] = Field(default_factory=list)
    immutable: bool = True
    published_at: datetime
    r2_key: str = ""
    def_r2_key: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


QualityGateVerdict = Literal["PASS", "REJECT"]


class QualityGateResult(_PlatformModel):
    verdict: QualityGateVerdict = "PASS"
    reasons: list[str] = Field(default_factory=list)


class DatasetBuildInject(_PlatformModel):
    """Fake golden 注入：可绕过 gate 或模拟违规。"""

    gate_override: dict[str, Any] | None = None
    skip_immutability: bool = False
    force_empty_snapshot: bool = False
    force_pit_false: bool = False
    strip_checksums: bool = False


def definition_summary(definition: DatasetDefinition) -> dict[str, Any]:
    """写入 def.json 的稳定摘要（完整 definition JSON）。"""
    return definition.model_dump(mode="json")


__all__ = [
    "ENGINE_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "DatasetBuildInject",
    "DatasetLineageItem",
    "DatasetManifest",
    "QualityGateResult",
    "QualityGateVerdict",
    "definition_summary",
]
