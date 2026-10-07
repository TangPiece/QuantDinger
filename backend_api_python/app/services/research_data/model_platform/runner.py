"""ModelPlatformService：9F-1 对外门面（Registry，无 train/LIVE）。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .artifact_store import ModelArtifactStore
from .bridge_legacy import to_legacy_model_definition, to_legacy_model_version_record
from .catalog import ModelCatalog
from .hashing import compute_model_config_hash
from .immutability import (
    ModelImmutabilityError,
    assert_training_run_immutable,
    assert_version_immutable,
    load_json_model,
)
from .lifecycle import (
    ModelLifecycleError,
    assert_transition,
    can_activate,
    can_deprecate,
    can_retire,
)
from .pin import pin_model, pin_model_artifact, pin_model_version, pin_training_run
from .protocol import (
    ENGINE_VERSION,
    Model,
    ModelArtifact,
    ModelArtifactSpec,
    ModelPlatformInject,
    ModelSearchQuery,
    ModelSpec,
    ModelVersion,
    ModelVersionLifecycle,
    ModelVersionSpec,
    TrainingRun,
    TrainingRunSpec,
)
from .search import search_models, search_versions
from .writers import write_artifact, write_model, write_training_run, write_version


class ModelPlatformError(RuntimeError):
    pass


def _coerce_inject(
    inject: Mapping[str, Any] | ModelPlatformInject | None,
) -> ModelPlatformInject | None:
    if inject is None:
        return None
    if isinstance(inject, ModelPlatformInject):
        return inject
    section = inject.get("model_platform") if isinstance(inject, dict) else None
    if isinstance(section, dict):
        return ModelPlatformInject.model_validate(section)
    if isinstance(inject, dict) and any(k in inject for k in ModelPlatformInject.model_fields):
        return ModelPlatformInject.model_validate(inject)
    return None


class ModelPlatformService:
    """Model Contract & Registry（无 train / predict / evaluate_model / auto_live）。"""

    def __init__(
        self,
        store: Path | ModelArtifactStore | None,
        registry: Any | None = None,
    ) -> None:
        if isinstance(store, ModelArtifactStore):
            self._store = store
        elif isinstance(store, Path):
            self._store = ModelArtifactStore(root=store)
        else:
            self._store = ModelArtifactStore()
        self._registry = registry
        self._catalog = ModelCatalog()
        self._runs: dict[str, TrainingRun] = {}
        self._artifacts: dict[str, ModelArtifact] = {}
        self._hydrate()

    @property
    def engine_version(self) -> str:
        return ENGINE_VERSION

    def _hydrate(self) -> None:
        for path in self._store.list_model_paths():
            m = load_json_model(path, Model)
            if m:
                self._catalog.upsert_model(m)
        for path in self._store.list_version_paths():
            v = load_json_model(path, ModelVersion)
            if v:
                self._catalog.upsert_version(v)
        for path in self._store.list_training_run_paths():
            r = load_json_model(path, TrainingRun)
            if r:
                self._runs[r.training_run_id] = r

    def compute_model_config_hash(self, config: dict[str, Any] | None) -> str:
        return compute_model_config_hash(config)

    def register_model(self, spec: ModelSpec | dict[str, Any]) -> Model:
        if isinstance(spec, dict):
            spec = ModelSpec.model_validate(spec)
        existing = self._catalog.get_model_by_code(spec.model_code)
        if existing is not None:
            raise ModelPlatformError(f"model_code already registered: {spec.model_code}")
        model = pin_model(spec)
        write_model(self._store, model)
        self._catalog.upsert_model(model)
        self._persist_registry_model(model)
        return model

    def get_model(self, model_id_or_code: str) -> Model:
        model = self._catalog.get_model(model_id_or_code)
        if model is None:
            model = self._catalog.get_model_by_code(model_id_or_code)
        if model is None:
            path = self._store.model_path(model_id=model_id_or_code)
            model = load_json_model(path, Model)
            if model:
                self._catalog.upsert_model(model)
        if model is None:
            raise ModelPlatformError(f"model not found: {model_id_or_code}")
        return model

    def register_version(
        self,
        model_id_or_code: str,
        spec: ModelVersionSpec | dict[str, Any],
        *,
        inject: Mapping[str, Any] | ModelPlatformInject | None = None,
    ) -> ModelVersion:
        inj = _coerce_inject(inject)
        if isinstance(spec, dict):
            spec = ModelVersionSpec.model_validate(spec)
        model = self.get_model(model_id_or_code)
        # duplicate version check
        for v in self._catalog.list_versions(model.model_id):
            if v.version == spec.version:
                raise ModelPlatformError(
                    f"version already exists: {model.model_code}@{spec.version}"
                )
        framework = spec.framework or model.framework
        spec = spec.model_copy(update={"framework": framework})
        version = pin_model_version(
            model_id=model.model_id,
            model_code=model.model_code,
            spec=spec,
            lifecycle="DRAFT",
        )
        write_version(self._store, version)
        self._catalog.upsert_version(version)
        self._persist_registry_version(version)
        if inj and inj.auto_activate:
            # 需先走 APPROVED；auto_activate 仅用于测试捷径：直接推到 APPROVED 再 ACTIVE
            for target in ("TRAINING", "TRAINED", "EVALUATING", "VALIDATED", "APPROVED"):
                version = self.transition(version.model_version_id, target)  # type: ignore[arg-type]
            return self.activate(version.model_version_id)
        return version

    def get_version(self, model_version_id_or_ref: str) -> ModelVersion:
        version = self._catalog.get_version(model_version_id_or_ref)
        if version is None:
            version = self._catalog.get_version_by_ref(model_version_id_or_ref)
        if version is None:
            path = self._store.version_path(model_version_id=model_version_id_or_ref)
            version = load_json_model(path, ModelVersion)
            if version:
                self._catalog.upsert_version(version)
        if version is None:
            raise ModelPlatformError(f"model version not found: {model_version_id_or_ref}")
        return version

    def list_versions(self, model_id_or_code: str) -> list[ModelVersion]:
        model = self.get_model(model_id_or_code)
        return self._catalog.list_versions(model.model_id)

    def search(
        self, query: ModelSearchQuery | dict[str, Any]
    ) -> dict[str, list[Any]]:
        if isinstance(query, dict):
            query = ModelSearchQuery.model_validate(query)
        return {
            "models": search_models(self._catalog.list_models(), query),
            "versions": search_versions(self._catalog.list_versions(), query),
        }

    def create_training_run(
        self,
        spec: TrainingRunSpec | dict[str, Any],
        *,
        inject: Mapping[str, Any] | ModelPlatformInject | None = None,
    ) -> TrainingRun:
        inj = _coerce_inject(inject)
        if isinstance(spec, dict):
            spec = TrainingRunSpec.model_validate(spec)
        run = pin_training_run(spec)
        path = self._store.training_run_path(training_run_id=run.training_run_id)
        existing = load_json_model(path, TrainingRun)
        if existing is not None:
            if inj and inj.skip_immutability:
                pass
            else:
                try:
                    assert_training_run_immutable(existing, run)
                except ModelImmutabilityError as exc:
                    raise ModelPlatformError(str(exc)) from exc
                return existing
        write_training_run(self._store, run)
        self._runs[run.training_run_id] = run
        return run

    def get_training_run(self, training_run_id: str) -> TrainingRun:
        run = self._runs.get(training_run_id)
        if run is None:
            path = self._store.training_run_path(training_run_id=training_run_id)
            run = load_json_model(path, TrainingRun)
            if run:
                self._runs[training_run_id] = run
        if run is None:
            raise ModelPlatformError(f"training run not found: {training_run_id}")
        return run

    def register_artifact(
        self,
        spec: ModelArtifactSpec | dict[str, Any],
    ) -> ModelArtifact:
        if isinstance(spec, dict):
            spec = ModelArtifactSpec.model_validate(spec)
        # ensure version exists
        self.get_version(spec.model_version_id)
        art = pin_model_artifact(spec)
        write_artifact(self._store, art)
        self._artifacts[art.artifact_id] = art
        # bind artifact_id onto version (lifecycle field allowed)
        version = self.get_version(spec.model_version_id)
        updated = version.model_copy(update={"artifact_id": art.artifact_id})
        write_version(self._store, updated)
        self._catalog.upsert_version(updated)
        return art

    def get_artifact(self, artifact_id: str) -> ModelArtifact:
        art = self._artifacts.get(artifact_id)
        if art is None:
            path = self._store.artifact_path(artifact_id=artifact_id)
            art = load_json_model(path, ModelArtifact)
            if art:
                self._artifacts[artifact_id] = art
        if art is None:
            raise ModelPlatformError(f"artifact not found: {artifact_id}")
        return art

    def transition(
        self,
        model_version_id: str,
        target: ModelVersionLifecycle,
    ) -> ModelVersion:
        version = self.get_version(model_version_id)
        assert_transition(version.lifecycle, target)
        updated = version.model_copy(update={"lifecycle": target})
        # lineage fields must not drift
        try:
            assert_version_immutable(version, updated)
        except ModelImmutabilityError as exc:
            raise ModelPlatformError(str(exc)) from exc
        write_version(self._store, updated)
        self._catalog.upsert_version(updated)
        return updated

    def activate(self, model_version_id: str) -> ModelVersion:
        version = self.get_version(model_version_id)
        if not can_activate(version.lifecycle):
            raise ModelLifecycleError(f"cannot activate from {version.lifecycle}")
        return self.transition(model_version_id, "ACTIVE")

    def deprecate(
        self,
        model_version_id: str,
        reason: str,
        *,
        replacement_ref: str = "",
    ) -> ModelVersion:
        version = self.get_version(model_version_id)
        if not can_deprecate(version.lifecycle):
            raise ModelLifecycleError(f"cannot deprecate from {version.lifecycle}")
        assert_transition(version.lifecycle, "DEPRECATED")
        updated = version.model_copy(
            update={
                "lifecycle": "DEPRECATED",
                "deprecate_reason": reason,
                "replacement_ref": replacement_ref,
            }
        )
        write_version(self._store, updated)
        self._catalog.upsert_version(updated)
        return updated

    def retire(self, model_version_id: str) -> ModelVersion:
        version = self.get_version(model_version_id)
        if not can_retire(version.lifecycle):
            raise ModelLifecycleError(f"cannot retire from {version.lifecycle}")
        return self.transition(model_version_id, "RETIRED")

    def to_legacy_definition(
        self, model_id_or_code: str, *, version: str | None = None
    ):
        model = self.get_model(model_id_or_code)
        ver = None
        if version:
            ver = self.get_version(f"{model.model_code}@{version}")
        return to_legacy_model_definition(model, ver)

    def to_legacy_version_record(self, model_version_id_or_ref: str):
        return to_legacy_model_version_record(self.get_version(model_version_id_or_ref))

    def _persist_registry_model(self, model: Model) -> None:
        if not self._registry or not hasattr(self._registry, "_read"):
            return
        with self._registry._lock:  # type: ignore[attr-defined]
            data = self._registry._read()
            data.setdefault("platform_models", {})[model.model_id] = model.model_dump(
                mode="json"
            )
            self._registry._write(data)

    def _persist_registry_version(self, version: ModelVersion) -> None:
        if not self._registry or not hasattr(self._registry, "_read"):
            return
        with self._registry._lock:  # type: ignore[attr-defined]
            data = self._registry._read()
            data.setdefault("platform_model_versions", {})[version.model_version_id] = (
                version.model_dump(mode="json")
            )
            self._registry._write(data)


__all__ = [
    "ModelPlatformError",
    "ModelPlatformService",
]
