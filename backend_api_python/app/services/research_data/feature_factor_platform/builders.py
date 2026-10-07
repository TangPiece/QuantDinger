"""构建：复用 FactorComputeService + 9A DatasetHandle。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from app.services.research_data.contracts import DatasetHandle, FeatureDefinition
from app.services.research_data.factor_lab import FactorComputeService, PITComputeContext
from app.services.research_data.factor_lab.compute.resolver import resolve_dependency_dag

from .artifact_store import FeatureFactorArtifactStore
from .feature_set import definition_from_manifest
from .immutability import FeatureFactorImmutabilityError, load_json_model
from .pin import pin_factor_build_index, pin_feature_set_build_index
from .protocol import (
    FactorBuildIndex,
    FactorBuildResult,
    FeatureBuildResult,
    FeatureFactorBuildInject,
    FeatureSetBuildIndex,
    FeatureSetManifest,
)
from .quality_gate import assert_quality_gate, evaluate_factor_build
from .taxonomy import assert_buildable_factor
from .writers import write_factor_build_index, write_feature_set_build_index


class _DatasetSvcLike(Protocol):
    def get(self, dataset_ref: str) -> DatasetHandle: ...

    def get_manifest(self, dataset_ref: str) -> Any: ...


class _RegistryLike(Protocol):
    def get_feature(self, feature_ref: str) -> FeatureDefinition: ...

    def get_factor_dataset(self, factor_dataset_id: str) -> Any: ...


class FactorBuildError(RuntimeError):
    pass


class FeatureFactorBuilder:
    def __init__(
        self,
        registry: _RegistryLike,
        *,
        compute: FactorComputeService | None = None,
        dataset_svc: _DatasetSvcLike | None = None,
        artifact_store: FeatureFactorArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._compute = compute
        self._dataset_svc = dataset_svc
        self._store = artifact_store or FeatureFactorArtifactStore()

    def build_factor(
        self,
        factor_ref: str,
        dataset_ref: str,
        *,
        window: tuple[str, str],
        layout: str = "long",
        inject: Mapping[str, Any] | FeatureFactorBuildInject | None = None,
    ) -> FactorBuildResult:
        if self._compute is None or self._dataset_svc is None:
            raise FactorBuildError("compute and dataset_svc required for build_factor")
        start_date, end_date = window
        handle = self._dataset_svc.get(dataset_ref)
        manifest_path = None
        if handle.manifest_uri:
            candidate = Path(str(handle.manifest_uri))
            if candidate.is_file():
                manifest_path = candidate
        if manifest_path is None:
            try:
                self._dataset_svc.get_manifest(dataset_ref)
            except Exception:
                pass

        feature = self._registry.get_feature(factor_ref)
        assert_buildable_factor(feature)
        resolve_dependency_dag(feature, self._registry)  # type: ignore[arg-type]

        gate = evaluate_factor_build(
            feature,
            handle,
            manifest_path=manifest_path,
            registry=self._registry,
            inject=inject,
        )
        assert_quality_gate(gate)

        inj = _coerce_inject(inject)
        index_path = self._store.factor_build_index_path(
            factor_ref=factor_ref,
            dataset_hash=handle.dataset_hash,
            layout=layout,
            start_date=start_date,
            end_date=end_date,
        )
        existing = load_json_model(index_path, FactorBuildIndex)
        expected_hash = str(feature.factor_hash or "")
        if existing and not (inj and inj.skip_immutability):
            if existing.factor_hash != expected_hash:
                raise FeatureFactorImmutabilityError(
                    f"build slot for {factor_ref} immutable; bump factor version"
                )
            return FactorBuildResult(
                factor_ref=factor_ref,
                factor_hash=existing.factor_hash,
                dataset_ref=dataset_ref,
                dataset_hash=handle.dataset_hash,
                layout=layout,  # type: ignore[arg-type]
                factor_dataset_id=existing.factor_dataset_id,
                manifest_uri=existing.manifest_uri,
                build_index_uri=str(index_path.resolve()),
            )

        ctx = PITComputeContext(
            knowledge_time=datetime.now(timezone.utc),
            snapshot_id=handle.definition.snapshot_id,
            start_date=start_date,
            end_date=end_date,
            exchange="CN",
            universe_code=handle.definition.universe_code,
            universe_version=handle.definition.universe_version,
            price_policy=handle.definition.price_policy,
            canonical_dataset_hash=handle.dataset_hash,
            processor_ref=handle.definition.processor,
        )
        meta = {"layout": layout, "dataset_ref": dataset_ref, "platform": "9b"}
        if inj and inj.compute_metadata:
            meta.update(inj.compute_metadata)

        result = self._compute.run(
            factor_ref,
            ctx,
            metadata=meta,
            feature=feature,
        )
        plan = result.plan
        if layout != plan.layout:
            plan = plan.model_copy(update={"layout": layout})  # type: ignore[arg-type]

        pinned = pin_factor_build_index(
            factor_ref=factor_ref,
            factor_hash=str(feature.factor_hash or plan.factor_hash),
            dataset_ref=dataset_ref,
            handle=handle,
            layout=layout,
            start_date=start_date,
            end_date=end_date,
            record=result.record,
            parquet_index=[{"storage_uri": result.record.storage_uri}],
        )
        write_result = write_factor_build_index(self._store, pinned)
        _append_build_index_registry(self._registry, pinned)
        return FactorBuildResult(
            factor_ref=factor_ref,
            factor_hash=pinned.factor_hash,
            dataset_ref=dataset_ref,
            dataset_hash=handle.dataset_hash,
            layout=layout,  # type: ignore[arg-type]
            factor_dataset_id=result.record.factor_dataset_id,
            manifest_uri=result.record.storage_uri or "",
            build_index_uri=write_result.path,
        )

    def build_feature_set(
        self,
        manifest: FeatureSetManifest,
        dataset_ref: str,
        *,
        window: tuple[str, str],
        layout: str = "long",
        inject: Mapping[str, Any] | FeatureFactorBuildInject | None = None,
    ) -> FeatureBuildResult:
        definition = definition_from_manifest(manifest)
        fs_ref = f"{definition.code}@{definition.version}"
        member_results: list[FactorBuildResult] = []
        member_payloads: list[dict[str, Any]] = []
        for member in definition.member_refs:
            br = self.build_factor(
                member,
                dataset_ref,
                window=window,
                layout=layout,
                inject=inject,
            )
            member_results.append(br)
            member_payloads.append(br.model_dump(mode="json"))

        handle = self._dataset_svc.get(dataset_ref) if self._dataset_svc else None
        if handle is None:
            raise FactorBuildError("dataset_svc required")
        start_date, end_date = window
        fs_index = pin_feature_set_build_index(
            feature_set_ref=fs_ref,
            feature_set_hash=manifest.feature_set_hash,
            dataset_ref=dataset_ref,
            handle=handle,
            layout=layout,
            start_date=start_date,
            end_date=end_date,
            member_builds=member_payloads,
        )
        wr = write_feature_set_build_index(self._store, fs_index)
        return FeatureBuildResult(
            feature_set_ref=fs_ref,
            feature_set_hash=manifest.feature_set_hash,
            dataset_ref=dataset_ref,
            dataset_hash=handle.dataset_hash,
            layout=layout,  # type: ignore[arg-type]
            member_builds=member_results,
            build_index_uri=wr.path,
        )


def _coerce_inject(
    inject: Mapping[str, Any] | FeatureFactorBuildInject | None,
) -> FeatureFactorBuildInject | None:
    if inject is None:
        return None
    if isinstance(inject, FeatureFactorBuildInject):
        return inject
    section = inject.get("feature_factor_platform") if isinstance(inject, dict) else None
    if isinstance(section, dict):
        return FeatureFactorBuildInject.model_validate(section)
    return None


def _append_build_index_registry(registry: Any, index: FactorBuildIndex) -> None:
    """LocalJson 旁路索引，供 list_by_dataset 扫描。"""
    if not hasattr(registry, "_read"):
        return
    with registry._lock:  # type: ignore[attr-defined]
        data = registry._read()
        data.setdefault("features", {})
        code, version = index.factor_ref.split("@", 1)
        key = f"{code}@{version}"
        raw = data["features"].get(key)
        if not raw:
            return
        sidecar = dict(raw.get("definition") or {})
        builds = list(sidecar.get("_platform_builds") or [])
        builds.append(
            {
                "factor_ref": index.factor_ref,
                "dataset_hash": index.dataset_hash,
                "factor_dataset_id": index.factor_dataset_id,
            }
        )
        sidecar["_platform_builds"] = builds
        raw["definition"] = sidecar
        data["features"][key] = raw
        registry._write(data)


__all__ = ["FactorBuildError", "FeatureFactorBuilder"]
