"""FeatureSet 定义与 manifest 组装。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .hashing import compute_feature_set_hash
from .identity import feature_set_r2_key
from .protocol import ENGINE_VERSION, FEATURE_SET_MANIFEST_SCHEMA, FeatureSetManifest


class FeatureSetDefinition(BaseModel):
    """FeatureSet 注册输入（成员为 feature/factor ref）。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str
    version: str
    name: str = ""
    member_refs: list[str] = Field(default_factory=list)
    processor: str = ""
    schema_version: str = "feature_set@1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AlphaDefinition(BaseModel):
    """Alpha 定义（仅注册）。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str
    version: str
    name: str = ""
    expression: str = ""
    factor_refs: list[str] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_feature_set_manifest(
    definition: FeatureSetDefinition,
    *,
    published_at: datetime | None = None,
) -> FeatureSetManifest:
    ts = published_at or datetime.now(timezone.utc)
    fhash = compute_feature_set_hash(
        code=definition.code,
        version=definition.version,
        member_refs=definition.member_refs,
        processor=definition.processor,
        schema_version=definition.schema_version,
    )
    return FeatureSetManifest(
        schema_version=FEATURE_SET_MANIFEST_SCHEMA,
        engine_version=ENGINE_VERSION,
        feature_set_code=definition.code,
        feature_set_version=definition.version,
        feature_set_hash=fhash,
        name=definition.name,
        member_refs=sorted(definition.member_refs),
        processor=definition.processor or "",
        schema_version_ref=definition.schema_version,
        immutable=True,
        published_at=ts,
        r2_key=feature_set_r2_key(code=definition.code, version=definition.version),
        metadata=dict(definition.metadata or {}),
    )


def definition_from_manifest(manifest: FeatureSetManifest) -> FeatureSetDefinition:
    return FeatureSetDefinition(
        code=manifest.feature_set_code,
        version=manifest.feature_set_version,
        name=manifest.name,
        member_refs=list(manifest.member_refs),
        processor=manifest.processor,
        schema_version=manifest.schema_version_ref,
        metadata=dict(manifest.metadata or {}),
    )


__all__ = [
    "AlphaDefinition",
    "FeatureSetDefinition",
    "build_feature_set_manifest",
    "definition_from_manifest",
]
