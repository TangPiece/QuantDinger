"""DatasetBuilder：gate → snapshot → registry → artifacts。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from app.services.research_data.contracts import DatasetDefinition, DatasetHandle

from .artifact_store import DatasetArtifactStore
from .hashing import compute_domain_dataset_hash
from .immutability import (
    DatasetImmutabilityError,
    assert_definition_immutable,
    assert_manifest_immutable,
    load_manifest_if_present,
)
from .identity import dataset_ref, logical_manifest_uri
from .pin import pin_manifest
from .protocol import DatasetBuildInject
from .quality_gate import assert_quality_gate, evaluate_dataset_build
from .writers import write_dataset_artifacts


class _RegistryLike(Protocol):
    def create_snapshot(
        self,
        *,
        snapshot_id: str,
        name: str,
        items: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str: ...

    def upsert_dataset(
        self,
        definition: DatasetDefinition,
        *,
        status: str = "ACTIVE",
        manifest_uri: str | None = None,
    ) -> None: ...

    def get_dataset(self, dataset_ref: str) -> DatasetHandle: ...


class DatasetBuilder:
    def __init__(
        self,
        registry: _RegistryLike,
        *,
        artifact_store: DatasetArtifactStore | None = None,
        prefer_local_manifest_uri: bool = True,
    ) -> None:
        self._registry = registry
        self._store = artifact_store or DatasetArtifactStore()
        self._prefer_local = prefer_local_manifest_uri

    def build_and_register(
        self,
        definition: DatasetDefinition,
        *,
        snapshot_items: list[dict[str, Any]],
        inject: Mapping[str, Any] | DatasetBuildInject | None = None,
        snapshot_name: str | None = None,
        status: str = "validated",
    ) -> DatasetHandle:
        gate = evaluate_dataset_build(definition, snapshot_items=snapshot_items, inject=inject)
        assert_quality_gate(gate)

        inj = _coerce_inject(inject)
        dataset_hash = compute_domain_dataset_hash(definition)
        manifest_path = self._store.manifest_path(definition)
        existing_manifest = load_manifest_if_present(manifest_path)

        ref = dataset_ref(definition)
        try:
            existing_handle = self._registry.get_dataset(ref)
            if not (inj and inj.skip_immutability):
                assert_definition_immutable(existing_handle.definition, definition)
        except KeyError:
            existing_handle = None

        if existing_manifest and not (inj and inj.skip_immutability):
            assert_manifest_immutable(existing_manifest, dataset_hash)

        self._registry.create_snapshot(
            snapshot_id=definition.snapshot_id,
            name=snapshot_name or f"{definition.code}@{definition.version}",
            items=snapshot_items,
            metadata={"dataset_hash": dataset_hash, "engine": "qd_dataset_platform@1"},
        )

        logical_uri = logical_manifest_uri(definition)
        write_result = write_dataset_artifacts(
            self._store,
            definition=definition,
            manifest=pin_manifest(
                definition,
                snapshot_items=snapshot_items,
                dataset_hash=dataset_hash,
                published_at=datetime.now(timezone.utc),
            ),
            manifest_uri=logical_uri,
        )
        manifest_uri = (
            write_result.manifest_path
            if self._prefer_local
            else logical_uri
        )

        self._registry.upsert_dataset(
            definition, status=status, manifest_uri=manifest_uri
        )
        handle = self._registry.get_dataset(ref)
        if not handle.manifest_uri:
            handle = handle.model_copy(update={"manifest_uri": manifest_uri})
        return handle


def _coerce_inject(
    inject: Mapping[str, Any] | DatasetBuildInject | None,
) -> DatasetBuildInject | None:
    if inject is None:
        return None
    if isinstance(inject, DatasetBuildInject):
        return inject
    section = inject.get("dataset_platform") if isinstance(inject, dict) else None
    if isinstance(section, dict):
        return DatasetBuildInject.model_validate(section)
    if isinstance(inject, dict):
        return DatasetBuildInject.model_validate(
            {k: v for k, v in inject.items() if k in DatasetBuildInject.model_fields}
        )
    return None


__all__ = ["DatasetBuilder", "DatasetImmutabilityError"]
