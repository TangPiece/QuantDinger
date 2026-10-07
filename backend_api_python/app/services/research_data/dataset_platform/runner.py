"""ResearchDatasetService：9A 对外门面。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from app.services.research_data.contracts import DatasetDefinition, DatasetHandle

from .artifact_store import DatasetArtifactStore
from .builder import DatasetBuilder
from .hashing import compute_domain_dataset_hash
from .immutability import DatasetImmutabilityError, assert_manifest_immutable, load_manifest_if_present
from .protocol import DatasetBuildInject, DatasetManifest, ENGINE_VERSION
from .quality_gate import DatasetQualityGateError


class DatasetPlatformError(RuntimeError):
    pass


class _RegistryLike(Protocol):
    def upsert_dataset(
        self,
        definition: DatasetDefinition,
        *,
        status: str = "ACTIVE",
        manifest_uri: str | None = None,
    ) -> None: ...

    def get_dataset(self, dataset_ref: str) -> DatasetHandle: ...

    def create_snapshot(
        self,
        *,
        snapshot_id: str,
        name: str,
        items: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str: ...


class _QueryLike(Protocol):
    def dataset(self, dataset_ref: str) -> DatasetHandle: ...


class ResearchDatasetService:
    def __init__(
        self,
        store: Path | DatasetArtifactStore | None,
        registry: _RegistryLike,
        *,
        query: _QueryLike | None = None,
    ) -> None:
        if isinstance(store, DatasetArtifactStore):
            self._store = store
        elif isinstance(store, Path):
            self._store = DatasetArtifactStore(root=store)
        else:
            self._store = DatasetArtifactStore()
        self._registry = registry
        self._query = query
        self._builder = DatasetBuilder(registry, artifact_store=self._store)

    @property
    def engine_version(self) -> str:
        return ENGINE_VERSION

    def build_and_register(
        self,
        definition: DatasetDefinition,
        *,
        snapshot_items: list[dict[str, Any]],
        inject: Mapping[str, Any] | DatasetBuildInject | None = None,
    ) -> DatasetHandle:
        try:
            return self._builder.build_and_register(
                definition, snapshot_items=snapshot_items, inject=inject
            )
        except DatasetQualityGateError as exc:
            raise DatasetPlatformError(str(exc)) from exc
        except DatasetImmutabilityError as exc:
            raise DatasetPlatformError(str(exc)) from exc

    def get(self, dataset_ref: str) -> DatasetHandle:
        handle = self._registry.get_dataset(dataset_ref)
        if handle.manifest_uri:
            return handle
        local = self._local_manifest_uri(handle.definition)
        if local:
            return handle.model_copy(update={"manifest_uri": local})
        from .identity import logical_manifest_uri

        return handle.model_copy(update={"manifest_uri": logical_manifest_uri(handle.definition)})

    def get_manifest(self, dataset_ref: str) -> DatasetManifest:
        handle = self.get(dataset_ref)
        path = self._manifest_file(handle.definition)
        if not path.is_file():
            raise DatasetPlatformError(f"manifest missing for {dataset_ref}: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        manifest = DatasetManifest.model_validate(data)
        if manifest.dataset_hash != handle.dataset_hash:
            raise DatasetPlatformError(
                f"manifest hash mismatch for {dataset_ref}: "
                f"{manifest.dataset_hash[:12]} vs {handle.dataset_hash[:12]}"
            )
        return manifest

    def assert_immutable(self, dataset_ref: str) -> None:
        handle = self.get(dataset_ref)
        path = self._manifest_file(handle.definition)
        existing = load_manifest_if_present(path)
        if existing is None:
            return
        incoming = compute_domain_dataset_hash(handle.definition)
        assert_manifest_immutable(existing, incoming)

    def list_datasets(self, code_prefix: str | None = None) -> list[str]:
        """列出 registry 中的 dataset_ref（LocalJson 优先）。"""
        refs = _list_from_registry(self._registry)
        if code_prefix is None:
            return sorted(refs)
        prefix = str(code_prefix)
        return sorted(r for r in refs if r.split("@", 1)[0].startswith(prefix))

    def dataquery_dataset(self, dataset_ref: str) -> DatasetHandle:
        if self._query is None:
            raise DatasetPlatformError("DataQuery not configured")
        return self._query.dataset(dataset_ref)

    def _manifest_file(self, definition: DatasetDefinition) -> Path:
        return self._store.manifest_path(definition)

    def _local_manifest_uri(self, definition: DatasetDefinition) -> str:
        path = self._manifest_file(definition)
        if path.is_file():
            return str(path.resolve())
        return ""


def _list_from_registry(registry: _RegistryLike) -> list[str]:
    if hasattr(registry, "_read"):
        data = registry._read()  # type: ignore[attr-defined]
        return list(data.get("datasets") or {})
    # D1 / 其它：无法枚举时返回空
    return []


__all__ = [
    "DatasetPlatformError",
    "ResearchDatasetService",
]
