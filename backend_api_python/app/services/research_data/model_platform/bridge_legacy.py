"""映射到 Phase 2D contracts（不破坏既有 ModelDefinition）。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.contracts import ModelDefinition, ModelVersionRecord

from .protocol import Model, ModelVersion


def to_legacy_model_definition(model: Model, version: ModelVersion | None = None) -> ModelDefinition:
    """薄映射：平台 Model(+Version) → 2D ModelDefinition。"""
    engine = (version.framework if version and version.framework else model.framework).lower()
    if engine not in ("lightgbm",):
        # 2D contract 仅允许 lightgbm；其它框架仍用占位 engine 字段在 metadata
        engine = "lightgbm"
    config: dict[str, Any] = {}
    if version and isinstance(version.metadata.get("config"), dict):
        config = dict(version.metadata["config"])
    ver = version.version if version else "0.0.0"
    return ModelDefinition(
        code=model.model_code,
        version=ver,
        name=model.name,
        engine=engine,  # type: ignore[arg-type]
        config=config,
    )


def to_legacy_model_version_record(version: ModelVersion) -> ModelVersionRecord:
    config: dict[str, Any] = {}
    if isinstance(version.metadata.get("config"), dict):
        config = dict(version.metadata["config"])
    return ModelVersionRecord(
        model_code=version.model_code,
        version=version.version,
        config=config,
        artifact_id=version.artifact_id or None,
        metrics={},
        dataset_ref=None,
        processor_ref=version.processor_version or None,
    )


__all__ = [
    "to_legacy_model_definition",
    "to_legacy_model_version_record",
]
