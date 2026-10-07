"""ModelPlatformService：9F Registry + Lineage + TrainingRun（无 Qlib/LIVE）。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .artifact_store import ModelArtifactStore
from .bridge_legacy import to_legacy_model_definition, to_legacy_model_version_record
from .catalog import ModelCatalog
from .executor import StubExecutorError, run_finalizing_stage, run_prepare_stage, run_running_stage
from .hashing import compute_model_config_hash
from .immutability import (
    ModelImmutabilityError,
    assert_training_run_immutable,
    assert_training_run_status_transition,
    assert_version_immutable,
    is_terminal_status,
    load_json_model,
)
from .job import pin_training_job, run_spec_from_job
from .lifecycle import (
    ModelLifecycleError,
    assert_transition,
    can_activate,
    can_deprecate,
    can_retire,
)
from .lineage import (
    LineageValidationError,
    assert_checksum,
    assert_lineage_pass,
    lineage_view,
    validate_lineage_for_version,
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
    TrainingJob,
    TrainingJobSpec,
    TrainingRun,
    TrainingRunSpec,
    TrainingRunStatus,
)
from .repro import load_repro_manifest, write_repro_manifest
from .search import search_models, search_versions
from .writers import (
    write_artifact,
    write_model,
    write_training_job,
    write_training_run,
    write_version,
)


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
    """Model Contract & Lineage（无 train / predict / evaluate_model / auto_live）。"""

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
        self._jobs: dict[str, TrainingJob] = {}
        self._jobs_by_idem: dict[str, str] = {}
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
        for path in self._store.list_training_job_paths():
            j = load_json_model(path, TrainingJob)
            if j:
                self._jobs[j.job_id] = j
                if j.idempotency_key:
                    self._jobs_by_idem[j.idempotency_key] = j.job_id

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
        """正式路径：须 SUCCEEDED training_run；否则仅 allow_draft_stub。"""
        inj = _coerce_inject(inject)
        if isinstance(spec, dict):
            spec = ModelVersionSpec.model_validate(spec)
        model = self.get_model(model_id_or_code)
        for v in self._catalog.list_versions(model.model_id):
            if v.version == spec.version:
                raise ModelPlatformError(
                    f"version already exists: {model.model_code}@{spec.version}"
                )

        allow_stub = bool(inj and inj.allow_draft_stub)
        if allow_stub:
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
                for target in ("TRAINING", "TRAINED", "EVALUATING", "VALIDATED", "APPROVED"):
                    version = self.transition(version.model_version_id, target)  # type: ignore[arg-type]
                return self.activate(version.model_version_id)
            return version

        if not (spec.training_run_id or "").strip():
            raise ModelPlatformError(
                "register_version requires training_run_id or inject.allow_draft_stub"
            )
        return self.create_version_from_run(
            spec.training_run_id,
            version=spec.version,
            lineage_spec=spec,
            artifact_id=spec.artifact_id or None,
            inject=inject,
        )

    def create_version_from_run(
        self,
        training_run_id: str,
        *,
        version: str,
        lineage_spec: ModelVersionSpec | dict[str, Any] | None = None,
        artifact_spec: ModelArtifactSpec | dict[str, Any] | None = None,
        artifact_id: str | None = None,
        inject: Mapping[str, Any] | ModelPlatformInject | None = None,
    ) -> ModelVersion:
        """SUCCEEDED/FINALIZING TrainingRun → TRAINED ModelVersion + artifact + repro manifest。"""
        inj = _coerce_inject(inject)
        run = self.get_training_run(training_run_id)
        if run.status not in ("SUCCEEDED", "FINALIZING"):
            raise ModelPlatformError(
                f"training_run must be SUCCEEDED or FINALIZING, got {run.status}"
            )

        if lineage_spec is None:
            lineage_spec = ModelVersionSpec(version=version)
        elif isinstance(lineage_spec, dict):
            lineage_spec = ModelVersionSpec.model_validate(lineage_spec)
        else:
            lineage_spec = lineage_spec.model_copy(update={"version": version or lineage_spec.version})

        model_key = run.model_id or run.model_code
        if not model_key:
            raise ModelPlatformError("training_run missing model_id/model_code")
        model = self.get_model(model_key)

        for v in self._catalog.list_versions(model.model_id):
            if v.version == lineage_spec.version:
                raise ModelPlatformError(
                    f"version already exists: {model.model_code}@{lineage_spec.version}"
                )

        # fill from run
        updates: dict[str, Any] = {
            "training_run_id": run.training_run_id,
            "dataset_hash": lineage_spec.dataset_hash or run.dataset_hash,
            "feature_set_hash": lineage_spec.feature_set_hash or run.feature_set_hash,
            "random_seed": lineage_spec.random_seed or run.random_seed,
        }
        if run.hyperparameters and not lineage_spec.hyperparameters:
            updates["hyperparameters"] = dict(run.hyperparameters)
        if not lineage_spec.framework:
            updates["framework"] = model.framework
        if not lineage_spec.tags and model.tags:
            updates["tags"] = list(model.tags)
        lineage_spec = lineage_spec.model_copy(update=updates)

        cfg_hash = compute_model_config_hash(lineage_spec.config)
        # artifact first (need id for validation)
        art: ModelArtifact | None = None
        if artifact_id:
            art = self.get_artifact(artifact_id)
        elif artifact_spec is not None:
            if isinstance(artifact_spec, dict):
                artifact_spec = ModelArtifactSpec.model_validate(artifact_spec)
            # temporary version id placeholder — pin artifact after version created
            # validate checksum early
            try:
                expected = inj.expected_checksum if inj else ""
                assert_checksum(artifact_spec.checksum, expected=expected or "")
            except LineageValidationError as exc:
                raise ModelPlatformError(str(exc)) from exc
        else:
            raise ModelPlatformError("artifact_spec or artifact_id required")

        inject_map = inj.model_dump(mode="json") if inj else {}
        reasons = validate_lineage_for_version(
            spec=lineage_spec,
            training_run=run,
            artifact=art,
            model_config_hash=cfg_hash,
            inject=inject_map,
        )
        # artifact_id may be filled after pin — if only artifact_spec, strip artifact_id_missing for now
        if artifact_spec is not None and art is None:
            reasons = [r for r in reasons if r != "artifact_id_missing"]
            if not artifact_spec.checksum:
                reasons.append("artifact_checksum_missing")
        try:
            assert_lineage_pass(reasons)
        except LineageValidationError as exc:
            raise ModelPlatformError(str(exc)) from exc

        meta = dict(lineage_spec.metadata or {})
        if run.factor_portfolio_hash:
            meta["factor_portfolio_hash"] = run.factor_portfolio_hash
        lineage_spec = lineage_spec.model_copy(update={"metadata": meta})

        version_obj = pin_model_version(
            model_id=model.model_id,
            model_code=model.model_code,
            spec=lineage_spec,
            lifecycle="TRAINED",
        )

        if art is None and artifact_spec is not None:
            aspec = artifact_spec.model_copy(
                update={"model_version_id": version_obj.model_version_id}
            )
            art = pin_model_artifact(aspec)
            write_artifact(self._store, art)
            self._artifacts[art.artifact_id] = art
            version_obj = version_obj.model_copy(update={"artifact_id": art.artifact_id})
        elif art is not None:
            version_obj = version_obj.model_copy(update={"artifact_id": art.artifact_id})

        # final lineage check with artifact bound
        final_spec = lineage_spec.model_copy(
            update={"artifact_id": version_obj.artifact_id, "training_run_id": run.training_run_id}
        )
        reasons2 = validate_lineage_for_version(
            spec=final_spec,
            training_run=run,
            artifact=art,
            model_config_hash=version_obj.model_config_hash,
            inject=inject_map,
        )
        try:
            assert_lineage_pass(reasons2)
        except LineageValidationError as exc:
            raise ModelPlatformError(str(exc)) from exc

        write_version(self._store, version_obj)
        self._catalog.upsert_version(version_obj)
        self._persist_registry_version(version_obj)

        write_repro_manifest(
            self._store.root_path(),
            version_obj,
            training_run=run,
            artifact=art,
        )

        if inj and inj.auto_activate:
            for target in ("EVALUATING", "VALIDATED", "APPROVED"):
                version_obj = self.transition(version_obj.model_version_id, target)  # type: ignore[arg-type]
            return self.activate(version_obj.model_version_id)
        return version_obj

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

    def get_active_version(self, model_id_or_code: str) -> ModelVersion:
        versions = [
            v for v in self.list_versions(model_id_or_code) if v.lifecycle == "ACTIVE"
        ]
        if not versions:
            raise ModelPlatformError(f"no ACTIVE version for {model_id_or_code}")
        versions.sort(key=lambda v: v.created_at, reverse=True)
        return versions[0]

    def get_lineage(self, model_version_id: str) -> dict[str, Any]:
        version = self.get_version(model_version_id)
        run = None
        if version.training_run_id:
            try:
                run = self.get_training_run(version.training_run_id)
            except ModelPlatformError:
                run = None
        art = None
        if version.artifact_id:
            try:
                art = self.get_artifact(version.artifact_id)
            except ModelPlatformError:
                art = None
        repro = load_repro_manifest(
            self._store.root_path(), model_version_id=version.model_version_id
        )
        repro_path = ""
        if repro is not None:
            from .repro import repro_manifest_path

            repro_path = str(
                repro_manifest_path(
                    self._store.root_path(),
                    model_version_id=version.model_version_id,
                )
            )
        return lineage_view(
            version, training_run=run, artifact=art, repro_path=repro_path
        )

    def get_artifact_for_version(self, model_version_id: str) -> ModelArtifact:
        version = self.get_version(model_version_id)
        if not version.artifact_id:
            raise ModelPlatformError(
                f"version {model_version_id} has no artifact_id"
            )
        return self.get_artifact(version.artifact_id)

    def get_repro_manifest(self, model_version_id: str) -> dict[str, Any]:
        version = self.get_version(model_version_id)
        data = load_repro_manifest(
            self._store.root_path(), model_version_id=version.model_version_id
        )
        if data is None:
            raise ModelPlatformError(
                f"repro manifest not found for {model_version_id}"
            )
        return data

    def search(
        self, query: ModelSearchQuery | dict[str, Any]
    ) -> dict[str, list[Any]]:
        if isinstance(query, dict):
            query = ModelSearchQuery.model_validate(query)
        return {
            "models": search_models(self._catalog.list_models(), query),
            "versions": search_versions(self._catalog.list_versions(), query),
        }

    def submit_training_job(
        self,
        spec: TrainingJobSpec | dict[str, Any],
    ) -> TrainingJob:
        if isinstance(spec, dict):
            spec = TrainingJobSpec.model_validate(spec)
        # resolve model
        model = self.get_model(spec.model_id or spec.model_code)
        if not spec.force_new and spec.idempotency_key:
            existing_id = self._jobs_by_idem.get(spec.idempotency_key)
            if existing_id:
                job = self.get_job(existing_id)
                if job.status == "OPEN":
                    runs = self.list_runs_for_job(job.job_id)
                    if runs and not is_terminal_status(runs[-1].status):
                        return job
                    if runs and runs[-1].status == "SUCCEEDED":
                        return job
        job = pin_training_job(
            spec.model_copy(
                update={
                    "model_id": model.model_id,
                    "model_code": model.model_code,
                    "framework": spec.framework or model.framework,
                }
            )
        )
        run = self.create_training_run(run_spec_from_job(job))
        job = job.model_copy(update={"run_ids": [run.training_run_id]})
        write_training_job(self._store, job)
        self._jobs[job.job_id] = job
        if job.idempotency_key:
            self._jobs_by_idem[job.idempotency_key] = job.job_id
        return job

    def get_job(self, job_id: str) -> TrainingJob:
        job = self._jobs.get(job_id)
        if job is None:
            path = self._store.training_job_path(job_id=job_id)
            job = load_json_model(path, TrainingJob)
            if job:
                self._jobs[job_id] = job
        if job is None:
            raise ModelPlatformError(f"training job not found: {job_id}")
        return job

    def list_runs_for_job(self, job_id: str) -> list[TrainingRun]:
        job = self.get_job(job_id)
        out: list[TrainingRun] = []
        for rid in job.run_ids:
            try:
                out.append(self.get_training_run(rid))
            except ModelPlatformError:
                continue
        return out

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

    def update_training_run_status(
        self,
        training_run_id: str,
        status: TrainingRunStatus,
        *,
        failure_class: str = "",
        failure_reason: str = "",
        failure_detail: str = "",
        metrics: dict[str, Any] | None = None,
        logs_uri: str = "",
        metrics_uri: str = "",
        model_version_id: str = "",
    ) -> TrainingRun:
        run = self.get_training_run(training_run_id)
        try:
            assert_training_run_status_transition(run.status, status)
        except ModelImmutabilityError as exc:
            raise ModelPlatformError(str(exc)) from exc
        if run.status == status:
            return run
        now = datetime.now(timezone.utc)
        updates: dict[str, Any] = {"status": status}
        if status == "PREPARING":
            updates["lineage_frozen"] = True
            if run.started_at is None:
                updates["started_at"] = now
        if status == "RUNNING" and run.started_at is None:
            updates["started_at"] = now
        if status in ("SUCCEEDED", "FAILED", "CANCELLED"):
            updates["finished_at"] = now
            if run.started_at is None:
                updates["started_at"] = now
        if failure_class:
            updates["failure_class"] = failure_class
        if failure_reason:
            updates["failure_reason"] = failure_reason
        if failure_detail:
            updates["failure_detail"] = failure_detail
        if metrics is not None:
            updates["metrics"] = metrics
        if logs_uri:
            updates["logs_uri"] = logs_uri
        if metrics_uri:
            updates["metrics_uri"] = metrics_uri
        if model_version_id:
            updates["model_version_id"] = model_version_id
        updated = run.model_copy(update=updates)
        write_training_run(self._store, updated)
        self._runs[training_run_id] = updated
        return updated

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

    def execute_training_run(
        self,
        training_run_id: str,
        *,
        inject: Mapping[str, Any] | ModelPlatformInject | None = None,
    ) -> TrainingRun:
        """同步 Stub 编排：QUEUED→…→SUCCEEDED|FAILED|CANCELLED；成功则 create_version_from_run。"""
        inj = _coerce_inject(inject)
        run = self.get_training_run(training_run_id)
        if is_terminal_status(run.status):
            raise ModelPlatformError(f"training_run already terminal: {run.status}")
        if run.status != "QUEUED":
            raise ModelPlatformError(
                f"execute_training_run expects QUEUED, got {run.status}"
            )

        # PREPARING
        run = self.update_training_run_status(training_run_id, "PREPARING")
        try:
            run_prepare_stage(run, inject=inj)
        except StubExecutorError as exc:
            return self.update_training_run_status(
                training_run_id,
                "FAILED",
                failure_class=exc.failure_class,
                failure_reason=str(exc),
                failure_detail=exc.stage,
            )

        # RUNNING
        run = self.update_training_run_status(training_run_id, "RUNNING")
        try:
            logs_uri, metrics_uri, metrics = run_running_stage(
                self._store, run, inject=inj
            )
        except StubExecutorError as exc:
            if exc.failure_class == "CANCELLED":
                return self.update_training_run_status(
                    training_run_id,
                    "CANCELLED",
                    failure_class="CANCELLED",
                    failure_reason=str(exc),
                )
            return self.update_training_run_status(
                training_run_id,
                "FAILED",
                failure_class=exc.failure_class,
                failure_reason=str(exc),
                failure_detail=exc.stage,
            )

        # FINALIZING
        run = self.update_training_run_status(
            training_run_id,
            "FINALIZING",
            metrics=metrics,
            logs_uri=logs_uri,
            metrics_uri=metrics_uri,
        )
        try:
            checksum = run_finalizing_stage(run, inject=inj)
        except StubExecutorError as exc:
            return self.update_training_run_status(
                training_run_id,
                "FAILED",
                failure_class=exc.failure_class,
                failure_reason=str(exc),
                failure_detail=exc.stage,
            )

        model_version_id = ""
        if not (inj and inj.skip_create_version):
            version_label = run.requested_model_version or f"run-{run.training_run_id[-8:]}"
            lineage = ModelVersionSpec(
                version=version_label,
                dataset_hash=run.dataset_hash,
                snapshot_id=run.snapshot_id or (inj.snapshot_id if inj else ""),
                feature_set_id=run.feature_set_id or (inj.feature_set_id if inj else ""),
                feature_set_hash=run.feature_set_hash,
                label_hash=run.label_hash or (inj.label_hash if inj else ""),
                processor_version=run.processor_version
                or (inj.processor_version if inj else ""),
                config=dict(run.training_config or {}),
                hyperparameters=dict(run.hyperparameters or {}),
                framework=run.framework,
                framework_version=run.framework_version,
                code_version=run.code_version,
                environment_hash=run.environment_hash,
                random_seed=run.random_seed,
                training_run_id=run.training_run_id,
            )
            # fill from inject known if still empty
            if inj:
                if not lineage.snapshot_id and inj.known_hashes.get("snapshot_id"):
                    lineage = lineage.model_copy(
                        update={"snapshot_id": inj.known_hashes["snapshot_id"]}
                    )
                if not lineage.feature_set_id and inj.feature_set_id:
                    lineage = lineage.model_copy(update={"feature_set_id": inj.feature_set_id})
                if not lineage.label_hash and inj.label_hash:
                    lineage = lineage.model_copy(update={"label_hash": inj.label_hash})
                if not lineage.processor_version and inj.processor_version:
                    lineage = lineage.model_copy(
                        update={"processor_version": inj.processor_version}
                    )
            try:
                ver = self.create_version_from_run(
                    run.training_run_id,
                    version=version_label,
                    lineage_spec=lineage,
                    artifact_spec=ModelArtifactSpec(
                        model_version_id="pending",
                        artifact_uri=f"qd/artifacts/model/{run.training_run_id}/",
                        checksum=checksum,
                        framework=run.framework or "CUSTOM",
                        framework_version=run.framework_version,
                    ),
                    inject=inject,
                )
                model_version_id = ver.model_version_id
            except ModelPlatformError as exc:
                return self.update_training_run_status(
                    training_run_id,
                    "FAILED",
                    failure_class="ARTIFACT_ERROR",
                    failure_reason=str(exc),
                    failure_detail="FINALIZING",
                )

        run = self.update_training_run_status(
            training_run_id,
            "SUCCEEDED",
            model_version_id=model_version_id,
            metrics=metrics,
            logs_uri=logs_uri,
            metrics_uri=metrics_uri,
        )
        if run.job_id:
            job = self.get_job(run.job_id)
            closed = job.model_copy(
                update={
                    "status": "CLOSED",
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            write_training_job(self._store, closed)
            self._jobs[job.job_id] = closed
        return run

    def retry_training_run(self, training_run_id: str) -> TrainingRun:
        parent = self.get_training_run(training_run_id)
        if parent.status not in ("FAILED", "CANCELLED"):
            raise ModelPlatformError(
                f"retry requires FAILED/CANCELLED parent, got {parent.status}"
            )
        if not parent.job_id:
            raise ModelPlatformError("parent training_run missing job_id")
        job = self.get_job(parent.job_id)
        child = self.create_training_run(
            run_spec_from_job(
                job,
                parent_training_run_id=parent.training_run_id,
                retry_index=int(parent.retry_index) + 1,
            )
        )
        run_ids = list(job.run_ids) + [child.training_run_id]
        updated_job = job.model_copy(
            update={
                "run_ids": run_ids,
                "status": "OPEN",
                "updated_at": datetime.now(timezone.utc),
            }
        )
        write_training_job(self._store, updated_job)
        self._jobs[job.job_id] = updated_job
        return child

    def cancel_training_run(self, training_run_id: str) -> TrainingRun:
        run = self.get_training_run(training_run_id)
        if run.status == "QUEUED":
            return self.update_training_run_status(
                training_run_id,
                "CANCELLED",
                failure_class="CANCELLED",
                failure_reason="cancelled_while_queued",
            )
        if run.status == "RUNNING":
            return self.update_training_run_status(
                training_run_id,
                "CANCELLED",
                failure_class="CANCELLED",
                failure_reason="cancelled_while_running",
            )
        raise ModelPlatformError(f"cannot cancel from status {run.status}")

    def register_artifact(
        self,
        spec: ModelArtifactSpec | dict[str, Any],
        *,
        inject: Mapping[str, Any] | ModelPlatformInject | None = None,
    ) -> ModelArtifact:
        """仅 DRAFT stub 可后绑 artifact；正式 version 须在 create_version_from_run 绑定。"""
        inj = _coerce_inject(inject)
        if isinstance(spec, dict):
            spec = ModelArtifactSpec.model_validate(spec)
        version = self.get_version(spec.model_version_id)
        if version.artifact_id:
            raise ModelPlatformError(
                f"artifact_id already bound to {version.artifact_id}; rebinding forbidden"
            )
        if version.lifecycle != "DRAFT":
            raise ModelPlatformError(
                "cannot bind artifact to formal version after create; use create_version_from_run"
            )
        try:
            assert_checksum(
                spec.checksum,
                expected=(inj.expected_checksum if inj else "") or "",
            )
        except LineageValidationError as exc:
            raise ModelPlatformError(str(exc)) from exc

        art = pin_model_artifact(spec)
        write_artifact(self._store, art)
        self._artifacts[art.artifact_id] = art
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

    def delete_version(self, model_version_id: str) -> None:
        raise ModelPlatformError(
            f"delete_version forbidden for immutable ModelVersion: {model_version_id}"
        )

    def transition(
        self,
        model_version_id: str,
        target: ModelVersionLifecycle,
    ) -> ModelVersion:
        version = self.get_version(model_version_id)
        assert_transition(version.lifecycle, target)
        updated = version.model_copy(update={"lifecycle": target})
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
        try:
            assert_version_immutable(version, updated)
        except ModelImmutabilityError as exc:
            raise ModelPlatformError(str(exc)) from exc
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
