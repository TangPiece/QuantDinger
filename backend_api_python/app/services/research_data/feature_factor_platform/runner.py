"""FeatureFactorService：9B 对外门面。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from app.services.research_data.contracts import FeatureDefinition
from app.services.research_data.factor_lab import (
    FactorComputeService,
    register_factor as lab_register_factor,
)
from app.services.research_data.factor_lab.dependencies import FactorDependencyError
from app.services.research_data.factor_lab.immutability import (
    FeatureImmutabilityError as LabFeatureImmutabilityError,
    assert_feature_immutable,
)
from app.services.research_data.registry import FeatureImmutabilityError

from .artifact_store import FeatureFactorArtifactStore
from .builders import FeatureFactorBuilder, FactorBuildError
from .feature_set import (
    AlphaDefinition,
    FeatureSetDefinition,
    build_feature_set_manifest,
    definition_from_manifest,
)
from .hashing import compute_feature_set_hash as _compute_feature_set_hash
from .identity import feature_set_ref as fs_ref_key
from .immutability import (
    FeatureFactorImmutabilityError,
    assert_feature_set_immutable,
    load_json_model,
)
from .lineage import build_lineage, list_by_dataset
from .pipeline import FactorPipelineSpec, merge_pipeline_into_definition
from .protocol import (
    ENGINE_VERSION,
    FactorBuildIndex,
    FactorBuildResult,
    FeatureBuildResult,
    FeatureFactorBuildInject,
    FeatureSetManifest,
    LineageNode,
)
from .quality_gate import (
    FeatureFactorQualityGateError,
    assert_quality_gate,
    evaluate_register_alpha,
    evaluate_register_feature,
    evaluate_register_factor,
    evaluate_feature_set,
)
from .taxonomy import AssetKind, TaxonomyError, with_asset_kind
from .writers import write_feature_set_manifest


class FeatureFactorPlatformError(RuntimeError):
    pass


class _RegistryLike(Protocol):
    def upsert_feature(self, feature: FeatureDefinition) -> None: ...

    def get_feature(self, feature_ref: str) -> FeatureDefinition: ...

    def get_dataset(self, dataset_ref: str) -> Any: ...


class _DatasetSvcLike(Protocol):
    def get(self, dataset_ref: str) -> Any: ...

    def get_manifest(self, dataset_ref: str) -> Any: ...


class FeatureFactorService:
    """Feature / Factor / FeatureSet 注册与构建（无挖掘 / 无 9C 评价门面）。"""

    def __init__(
        self,
        store: Path | FeatureFactorArtifactStore | None,
        registry: _RegistryLike,
        *,
        query: Any = None,
        dataset_svc: _DatasetSvcLike | None = None,
        compute: FactorComputeService | None = None,
    ) -> None:
        if isinstance(store, FeatureFactorArtifactStore):
            self._store = store
        elif isinstance(store, Path):
            self._store = FeatureFactorArtifactStore(root=store)
        else:
            self._store = FeatureFactorArtifactStore()
        self._registry = registry
        self._dataset_svc = dataset_svc
        self._compute = compute
        self._builder = FeatureFactorBuilder(
            registry,
            compute=compute,
            dataset_svc=dataset_svc,
            artifact_store=self._store,
        )

    @property
    def engine_version(self) -> str:
        return ENGINE_VERSION

    def register_feature(self, definition: FeatureDefinition) -> FeatureDefinition:
        try:
            assert_quality_gate(evaluate_register_feature(definition))
            feat = with_asset_kind(definition, AssetKind.FEATURE)
            return self._register_locked(feat)
        except (FeatureFactorQualityGateError, TaxonomyError) as exc:
            raise FeatureFactorPlatformError(str(exc)) from exc

    def register_factor(
        self,
        definition: FeatureDefinition,
        pipeline: FactorPipelineSpec | None = None,
    ) -> FeatureDefinition:
        try:
            assert_quality_gate(evaluate_register_factor(definition, pipeline))
            sidecar = merge_pipeline_into_definition(definition.definition, pipeline)
            feat = with_asset_kind(definition, AssetKind.FACTOR, extra_definition=sidecar)
            return self._register_locked(feat)
        except (FeatureFactorQualityGateError, TaxonomyError) as exc:
            raise FeatureFactorPlatformError(str(exc)) from exc

    def register_alpha(self, alpha: AlphaDefinition) -> FeatureDefinition:
        try:
            feat = FeatureDefinition(
                code=alpha.code,
                version=alpha.version,
                name=alpha.name,
                expression=alpha.expression,
                dependencies=[f"factor:{r}" for r in alpha.factor_refs],
                definition={
                    "asset_kind": AssetKind.ALPHA.value,
                    "weights": alpha.weights,
                    **(alpha.metadata or {}),
                },
            )
            assert_quality_gate(evaluate_register_alpha(feat))
            return self._register_locked(feat)
        except (FeatureFactorQualityGateError, TaxonomyError) as exc:
            raise FeatureFactorPlatformError(str(exc)) from exc

    def register_feature_set(self, definition: FeatureSetDefinition) -> FeatureSetManifest:
        try:
            assert_quality_gate(evaluate_feature_set(definition))
            manifest = build_feature_set_manifest(definition)
            path = self._store.feature_set_manifest_path(
                code=definition.code, version=definition.version
            )
            existing = load_json_model(path, FeatureSetManifest)
            if existing is not None:
                assert_feature_set_immutable(existing, definition)
            write_feature_set_manifest(self._store, definition, manifest)
            self._persist_feature_set_manifest(manifest)
            return manifest
        except (FeatureFactorQualityGateError, FeatureFactorImmutabilityError) as exc:
            raise FeatureFactorPlatformError(str(exc)) from exc

    def build_factor(
        self,
        factor_ref: str,
        dataset_ref: str,
        *,
        window: tuple[str, str],
        layout: str = "long",
        inject: Mapping[str, Any] | FeatureFactorBuildInject | None = None,
    ) -> FactorBuildResult:
        try:
            return self._builder.build_factor(
                factor_ref,
                dataset_ref,
                window=window,
                layout=layout,
                inject=inject,
            )
        except (
            FeatureFactorQualityGateError,
            FeatureFactorImmutabilityError,
            FactorBuildError,
            TaxonomyError,
        ) as exc:
            raise FeatureFactorPlatformError(str(exc)) from exc

    def build_feature_set(
        self,
        feature_set_ref: str,
        dataset_ref: str,
        *,
        window: tuple[str, str],
        layout: str = "long",
        inject: Mapping[str, Any] | FeatureFactorBuildInject | None = None,
    ) -> FeatureBuildResult:
        manifest = self.get_manifest(feature_set_ref)
        try:
            return self._builder.build_feature_set(
                manifest,
                dataset_ref,
                window=window,
                layout=layout,
                inject=inject,
            )
        except (FeatureFactorQualityGateError, FeatureFactorImmutabilityError, FactorBuildError) as exc:
            raise FeatureFactorPlatformError(str(exc)) from exc

    def get_lineage(self, ref: str, *, dataset_ref: str | None = None) -> LineageNode:
        return build_lineage(self._registry, ref, dataset_ref=dataset_ref)

    def list_by_dataset(self, dataset_hash: str) -> list[str]:
        return list_by_dataset(self._registry, dataset_hash)

    def get_manifest(self, ref: str) -> FeatureSetManifest:
        if "@" not in ref:
            raise FeatureFactorPlatformError(f"invalid feature_set_ref: {ref!r}")
        code, version = ref.split("@", 1)
        definition = FeatureSetDefinition(code=code, version=version, member_refs=[])
        path = self._store.feature_set_manifest_path(code=code, version=version)
        if not path.is_file():
            stored = self._load_feature_set_from_registry(ref)
            if stored is None:
                raise FeatureFactorPlatformError(f"feature_set manifest missing: {ref}")
            return stored
        data = json.loads(path.read_text(encoding="utf-8"))
        return FeatureSetManifest.model_validate(data)

    def assert_immutable(self, feature_set_ref: str) -> None:
        manifest = self.get_manifest(feature_set_ref)
        definition = definition_from_manifest(manifest)
        incoming_hash = _compute_feature_set_hash(
            code=definition.code,
            version=definition.version,
            member_refs=definition.member_refs,
            processor=definition.processor,
            schema_version=definition.schema_version,
        )
        if manifest.feature_set_hash != incoming_hash:
            raise FeatureFactorPlatformError(
                f"feature_set {feature_set_ref} manifest hash drift"
            )

    def get_factor_build_index(
        self,
        factor_ref: str,
        dataset_hash: str,
        *,
        layout: str = "long",
        start_date: str,
        end_date: str,
    ) -> FactorBuildIndex:
        path = self._store.factor_build_index_path(
            factor_ref=factor_ref,
            dataset_hash=dataset_hash,
            layout=layout,
            start_date=start_date,
            end_date=end_date,
        )
        idx = load_json_model(path, FactorBuildIndex)
        if idx is None:
            raise FeatureFactorPlatformError(f"build index missing: {path}")
        return idx

    def _register_locked(self, feat: FeatureDefinition) -> FeatureDefinition:
        ref = f"{feat.code}@{feat.version}"
        try:
            existing = self._registry.get_feature(ref)
            try:
                assert_feature_immutable(existing, feat)
            except LabFeatureImmutabilityError as exc:
                raise FeatureFactorPlatformError(str(exc)) from exc
            return existing
        except KeyError:
            pass
        try:
            return lab_register_factor(self._registry, feat)  # type: ignore[arg-type]
        except (
            FactorDependencyError,
            FeatureImmutabilityError,
            LabFeatureImmutabilityError,
        ) as exc:
            raise FeatureFactorPlatformError(str(exc)) from exc

    def _persist_feature_set_manifest(self, manifest: FeatureSetManifest) -> None:
        if not hasattr(self._registry, "_read"):
            return
        ref = f"{manifest.feature_set_code}@{manifest.feature_set_version}"
        with self._registry._lock:  # type: ignore[attr-defined]
            data = self._registry._read()
            data.setdefault("feature_sets", {})[ref] = manifest.model_dump(mode="json")
            self._registry._write(data)

    def _load_feature_set_from_registry(self, ref: str) -> FeatureSetManifest | None:
        if not hasattr(self._registry, "_read"):
            return None
        data = self._registry._read()
        raw = (data.get("feature_sets") or {}).get(ref)
        if not raw:
            return None
        return FeatureSetManifest.model_validate(raw)


__all__ = [
    "FeatureFactorPlatformError",
    "FeatureFactorService",
]
