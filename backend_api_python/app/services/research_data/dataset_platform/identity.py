"""Dataset 引用与 R2 键解析。"""

from __future__ import annotations

from app.services.research_data.contracts import DatasetDefinition
from app.services.research_data.paths import dataset_manifest_key, r2_uri


def split_dataset_ref(dataset_ref: str) -> tuple[str, str]:
    text = str(dataset_ref or "").strip()
    if "@" not in text:
        raise ValueError(f"invalid dataset_ref: {dataset_ref!r}")
    code, version = text.split("@", 1)
    if not code or not version:
        raise ValueError(f"invalid dataset_ref: {dataset_ref!r}")
    return code, version


def dataset_ref(definition: DatasetDefinition) -> str:
    return f"{definition.code}@{definition.version}"


def immutability_key(definition: DatasetDefinition) -> tuple[str, str, str]:
    """同 (code, version, snapshot_id) 视为同一发布槽位。"""
    return (definition.code, definition.version, definition.snapshot_id)


def dataset_definition_key(*, dataset_code: str, dataset_version: str) -> str:
    """``qd/dataset/{code}/{version}/def.json``。"""
    from app.services.research_data import config as rd_config

    root = rd_config.canonical_prefix()
    safe_code = str(dataset_code or "").replace("/", "_")
    safe_ver = str(dataset_version or "").replace("/", "_")
    return f"{root}/dataset/{safe_code}/{safe_ver}/def.json"


def manifest_r2_key(definition: DatasetDefinition) -> str:
    return dataset_manifest_key(
        dataset_code=definition.code,
        dataset_version=definition.version,
        snapshot_id=definition.snapshot_id,
    )


def logical_manifest_uri(definition: DatasetDefinition) -> str:
    """Registry 默认 manifest_uri（逻辑 R2 URI）。"""
    return r2_uri(manifest_r2_key(definition))


def logical_def_uri(definition: DatasetDefinition) -> str:
    return r2_uri(dataset_definition_key(dataset_code=definition.code, dataset_version=definition.version))


__all__ = [
    "dataset_definition_key",
    "dataset_ref",
    "immutability_key",
    "logical_def_uri",
    "logical_manifest_uri",
    "manifest_r2_key",
    "split_dataset_ref",
]
