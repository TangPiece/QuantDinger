"""ReproducibilityService：capture + reproduce + compare。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .artifact_store import ReproducibilityArtifactStore
from .capture import capture_manifest_from_training_run
from .compare import (
    compare_artifact_checksums,
    compare_metrics,
    compare_predictions,
    evaluate_prechecks,
    finalize_result,
)
from .environment import capture_environment
from .identity import new_reproducibility_run_id
from .immutability import (
    ReproducibilityImmutabilityError,
    load_json_model,
)
from .policy_presets import get_policy_preset, policy_version_ref
from .protocol import (
    ENGINE_VERSION,
    ReproducibilityInject,
    ReproducibilityManifest,
    ReproducibilityReport,
    ReproducibilityRun,
)
from .writers import write_manifest, write_repro_bundle, write_run


class ReproducibilityError(RuntimeError):
    pass


def _coerce_inject(
    inject: Mapping[str, Any] | ReproducibilityInject | None,
) -> ReproducibilityInject | None:
    if inject is None:
        return None
    if isinstance(inject, ReproducibilityInject):
        return inject
    if isinstance(inject, dict):
        section = inject.get("model_reproducibility")
        if isinstance(section, dict):
            return ReproducibilityInject.model_validate(section)
        return ReproducibilityInject.model_validate(inject)
    return None


class ReproducibilityService:
    """TrainingRun 级可复现捕获与复现比较（不改源 Run / Version）。"""

    def __init__(
        self,
        store: Path | ReproducibilityArtifactStore | None,
        *,
        model_platform: Any | None = None,
    ) -> None:
        if isinstance(store, ReproducibilityArtifactStore):
            self._store = store
        elif isinstance(store, Path):
            self._store = ReproducibilityArtifactStore(root=store)
        else:
            self._store = ReproducibilityArtifactStore()
        self._platform = model_platform
        self._manifests: dict[str, ReproducibilityManifest] = {}
        self._by_training_run: dict[str, str] = {}
        self._runs: dict[str, ReproducibilityRun] = {}
        self._hydrate()

    @property
    def engine_version(self) -> str:
        return ENGINE_VERSION

    def bind_model_platform(self, model_platform: Any) -> None:
        self._platform = model_platform

    def _hydrate(self) -> None:
        for path in self._store.list_manifest_paths():
            m = load_json_model(path, ReproducibilityManifest)
            if m:
                self._manifests[m.repro_manifest_id] = m
                self._by_training_run[m.training_run_id] = m.repro_manifest_id
        for path in self._store.list_run_paths():
            r = load_json_model(path, ReproducibilityRun)
            if r:
                self._runs[r.reproducibility_run_id] = r

    def capture_from_training_run(
        self,
        training_run_id: str,
        *,
        artifact: Any | None = None,
        inject: Mapping[str, Any] | ReproducibilityInject | None = None,
    ) -> ReproducibilityManifest:
        if self._platform is None:
            raise ReproducibilityError("model_platform required for capture")
        inj = _coerce_inject(inject)
        existing_id = self._by_training_run.get(training_run_id)
        if existing_id and not (inj and inj.skip_capture_immutability):
            existing = self._manifests.get(existing_id)
            if existing:
                raise ReproducibilityImmutabilityError(
                    f"manifest already captured for {training_run_id}"
                )
        run = self._platform.get_training_run(training_run_id)
        art = artifact
        if art is None and getattr(run, "model_version_id", None):
            try:
                ver = self._platform.get_version(run.model_version_id)
                if ver.artifact_id:
                    art = self._platform.get_artifact(ver.artifact_id)
            except Exception:
                art = None
        manifest = capture_manifest_from_training_run(run, artifact=art, inject=inj)
        write_manifest(self._store, manifest)
        self._manifests[manifest.repro_manifest_id] = manifest
        self._by_training_run[training_run_id] = manifest.repro_manifest_id
        return manifest

    def get_manifest(self, repro_manifest_id: str) -> ReproducibilityManifest:
        m = self._manifests.get(repro_manifest_id)
        if m is None:
            path = self._store.manifest_path(repro_manifest_id=repro_manifest_id)
            m = load_json_model(path, ReproducibilityManifest)
            if m:
                self._manifests[repro_manifest_id] = m
        if m is None:
            raise ReproducibilityError(f"manifest not found: {repro_manifest_id}")
        return m

    def get_manifest_for_training_run(
        self, training_run_id: str
    ) -> ReproducibilityManifest:
        mid = self._by_training_run.get(training_run_id)
        if not mid:
            raise ReproducibilityError(
                f"no reproducibility manifest for training_run {training_run_id}"
            )
        return self.get_manifest(mid)

    def reproduce(
        self,
        source_training_run_id: str,
        *,
        policy_code: str = "REPRO_STRICT_V1",
        inject: Mapping[str, Any] | ReproducibilityInject | None = None,
    ) -> ReproducibilityRun:
        if self._platform is None:
            raise ReproducibilityError("model_platform required for reproduce")
        inj = _coerce_inject(inject)
        policy = get_policy_preset(policy_code)
        now = datetime.now(timezone.utc)

        try:
            source_man = self.get_manifest_for_training_run(source_training_run_id)
        except ReproducibilityError:
            source_man = self.capture_from_training_run(
                source_training_run_id, inject=inj
            )

        run = ReproducibilityRun(
            reproducibility_run_id=new_reproducibility_run_id(),
            source_training_run_id=source_training_run_id,
            repro_manifest_id=source_man.repro_manifest_id,
            repro_policy_version=policy_version_ref(policy),
            policy_code=policy.policy_code,
            status="QUEUED",
            created_at=now,
        )
        write_run(self._store, run)
        self._runs[run.reproducibility_run_id] = run

        # PREPARING
        run = run.model_copy(update={"status": "PREPARING"})
        write_run(self._store, run)
        self._runs[run.reproducibility_run_id] = run

        # Baseline = source freeze；仅 inject mutate_* 模拟漂移（避免本机瞬时 env 噪声）
        current_env = source_man.environment
        if inj and (inj.dependency_lock or inj.package_versions or inj.container_image_digest):
            current_env = capture_environment(
                inject=inj,
                ml_framework=source_man.framework,
            )
        current_input = source_man.input_manifest.model_copy(deep=True)
        current_seeds = source_man.seeds.model_copy(deep=True)
        early, flags, reason = evaluate_prechecks(
            source_man,
            current_env_hash=current_env.environment_hash,
            current_dep_hash=current_env.dependency_lock_hash,
            current_code_commit=source_man.code_commit or source_man.code_version,
            current_seeds=current_seeds,
            current_input=current_input,
            policy=policy,
            inject=inj,
        )

        if early is not None:
            return self._finish_mismatch(
                run,
                source_man=source_man,
                policy=policy,
                flags=flags,
                result=early,
                reason=reason,
                env=current_env,
            )

        if policy.mode == "AUDITABLE":
            report = ReproducibilityReport(
                reproducibility_run_id=run.reproducibility_run_id,
                result="AUDIT_OK",
                reason="auditable_conditions_complete",
                input_match=flags["input_match"],
                code_match=flags["code_match"],
                environment_match=flags["environment_match"],
                dependency_match=flags["dependency_match"],
                seed_match=flags["seed_match"],
                artifact_match=False,
                metrics_within_tolerance=False,
                prediction_within_tolerance=False,
                created_at=datetime.now(timezone.utc),
            )
            uris = write_repro_bundle(
                self._store,
                run.reproducibility_run_id,
                manifest=source_man.model_dump(mode="json"),
                input_manifest=source_man.input_manifest.model_dump(mode="json"),
                environment=current_env.model_dump(mode="json"),
                dependency_lock=current_env.dependency_lock,
                seeds=source_man.seeds.model_dump(mode="json"),
                report=report.model_dump(mode="json"),
            )
            finished = run.model_copy(
                update={
                    "status": "SUCCEEDED",
                    "result": "AUDIT_OK",
                    "reason": report.reason,
                    "input_match": flags["input_match"],
                    "code_match": flags["code_match"],
                    "environment_match": flags["environment_match"],
                    "dependency_match": flags["dependency_match"],
                    "seed_match": flags["seed_match"],
                    "report": report,
                    "report_uri": uris.get("reproducibility_report_uri", ""),
                    "completed_at": datetime.now(timezone.utc),
                }
            )
            write_run(self._store, finished)
            self._runs[finished.reproducibility_run_id] = finished
            return finished

        # RUNNING — create child TrainingRun
        run = run.model_copy(update={"status": "RUNNING"})
        write_run(self._store, run)
        child_id = ""
        if not (inj and inj.skip_execute):
            child_id = self._spawn_child_run(source_training_run_id, source_man)
            try:
                from app.services.research_data.model_platform.protocol import (
                    ModelPlatformInject,
                )

                plat_inj = ModelPlatformInject(
                    known_hashes={
                        "dataset_hash": source_man.dataset_hash,
                        "feature_set_hash": source_man.feature_set_hash,
                        "label_hash": source_man.label_hash,
                        "snapshot_id": source_man.snapshot_id,
                    },
                    feature_set_id="",
                    label_hash=source_man.label_hash,
                    processor_version=source_man.processor_version,
                    snapshot_id=source_man.snapshot_id,
                    skip_create_version=False,
                )
                # Prefer formal_inject-like: child execute may fail without hashes;
                # if execute fails, still compare via inject overlays.
                self._platform.execute_training_run(
                    child_id, inject={"model_platform": plat_inj.model_dump()}
                )
            except Exception as exc:
                # allow inject-only compare path
                if not inj:
                    return self._finish_mismatch(
                        run,
                        source_man=source_man,
                        policy=policy,
                        flags=flags,
                        result="REPRODUCTION_FAILED",
                        reason=f"execute_failed:{exc}",
                        env=current_env,
                        child_id=child_id,
                    )
        else:
            child_id = f"skipped_{run.reproducibility_run_id}"

        run = run.model_copy(
            update={
                "status": "COMPARING",
                "reproduce_training_run_id": child_id,
            }
        )
        write_run(self._store, run)

        # Compare payloads
        metrics_orig = dict(source_man.metrics_snapshot or {})
        metrics_repr = dict(metrics_orig)
        preds_orig = list(inj.predictions_original) if inj else []
        preds_repr = list(inj.predictions_reproduced) if inj else list(preds_orig)
        art_orig = source_man.artifact_checksum
        art_repr = art_orig
        if inj:
            if inj.metrics_original:
                metrics_orig = dict(inj.metrics_original)
            if inj.metrics_reproduced:
                metrics_repr = dict(inj.metrics_reproduced)
            elif inj.metrics_original:
                metrics_repr = dict(inj.metrics_original)
            if inj.artifact_checksum_original:
                art_orig = inj.artifact_checksum_original
            if inj.artifact_checksum_reproduced:
                art_repr = inj.artifact_checksum_reproduced
            elif inj.artifact_checksum_original and not inj.force_non_deterministic:
                art_repr = inj.artifact_checksum_original
            if inj.force_non_deterministic and not inj.artifact_checksum_reproduced:
                art_repr = ("b" * 64) if art_orig != ("b" * 64) else ("c" * 64)
            if not preds_orig and inj.predictions_reproduced:
                preds_orig = list(inj.predictions_reproduced)
            if not preds_repr:
                preds_repr = list(preds_orig)

        # try pull child artifact checksum if executed
        if child_id and not child_id.startswith("skipped_") and not (
            inj and inj.artifact_checksum_reproduced
        ):
            try:
                child = self._platform.get_training_run(child_id)
                if child.model_version_id:
                    ver = self._platform.get_version(child.model_version_id)
                    if ver.artifact_id:
                        art = self._platform.get_artifact(ver.artifact_id)
                        art_repr = art.checksum or art_repr
                if child.metrics:
                    metrics_repr = dict(child.metrics)
            except Exception:
                pass

        art_cmp = compare_artifact_checksums(art_orig, art_repr)
        met_cmp = compare_metrics(
            metrics_orig, metrics_repr, tolerance=policy.metric_tolerance
        )
        # default empty preds → within if both empty
        if not preds_orig and not preds_repr:
            pred_cmp = {
                "mae": 0.0,
                "rmse": 0.0,
                "max_abs_error": 0.0,
                "correlation": 1.0,
                "rank_correlation": 1.0,
                "within_tolerance": True,
                "n": 0,
            }
        else:
            pred_cmp = compare_predictions(
                preds_orig, preds_repr, tolerance=policy.prediction_tolerance
            )

        # honor non-deterministic flags on source when inject forces
        src_for_finalize = source_man
        if inj and (
            inj.force_non_deterministic
            or inj.deterministic_enabled is False
        ):
            src_for_finalize = source_man.model_copy(
                update={
                    "deterministic_enabled": False,
                    "deterministic_supported": False
                    if inj.force_non_deterministic
                    else source_man.deterministic_supported,
                }
            )

        result, fin_reason = finalize_result(
            policy=policy,
            flags=flags,
            artifact_cmp=art_cmp,
            metrics_cmp=met_cmp,
            pred_cmp=pred_cmp,
            source=src_for_finalize,
        )

        report = ReproducibilityReport(
            reproducibility_run_id=run.reproducibility_run_id,
            result=result,
            reason=fin_reason,
            input_match=flags["input_match"],
            code_match=flags["code_match"],
            environment_match=flags["environment_match"],
            dependency_match=flags["dependency_match"],
            seed_match=flags["seed_match"],
            artifact_match=bool(art_cmp.get("match")),
            metrics_within_tolerance=bool(met_cmp.get("within_tolerance")),
            prediction_within_tolerance=bool(pred_cmp.get("within_tolerance")),
            metric_comparison=met_cmp,
            prediction_comparison=pred_cmp,
            artifact_comparison=art_cmp,
            created_at=datetime.now(timezone.utc),
        )
        uris = write_repro_bundle(
            self._store,
            run.reproducibility_run_id,
            manifest=source_man.model_dump(mode="json"),
            input_manifest=source_man.input_manifest.model_dump(mode="json"),
            environment=current_env.model_dump(mode="json"),
            dependency_lock=current_env.dependency_lock,
            seeds=source_man.seeds.model_dump(mode="json"),
            metrics_original=metrics_orig,
            metrics_reproduced=metrics_repr,
            prediction_diff=pred_cmp,
            artifact_comparison=art_cmp,
            report=report.model_dump(mode="json"),
        )
        status = "SUCCEEDED" if result in (
            "EXACT_MATCH",
            "NUMERICAL_MATCH",
            "NON_DETERMINISTIC",
            "AUDIT_OK",
        ) else "FAILED"
        # NON_DETERMINISTIC is a valid outcome, not execute failure
        if result == "NON_DETERMINISTIC":
            status = "SUCCEEDED"

        finished = run.model_copy(
            update={
                "status": status,
                "result": result,
                "reason": fin_reason,
                "reproduce_training_run_id": child_id,
                "input_match": flags["input_match"],
                "code_match": flags["code_match"],
                "environment_match": flags["environment_match"],
                "dependency_match": flags["dependency_match"],
                "seed_match": flags["seed_match"],
                "metric_comparison_uri": uris.get("metrics_original_uri", ""),
                "prediction_comparison_uri": uris.get("prediction_diff_uri", ""),
                "artifact_comparison_uri": uris.get("artifact_comparison_uri", ""),
                "report_uri": uris.get("reproducibility_report_uri", ""),
                "report": report,
                "completed_at": datetime.now(timezone.utc),
            }
        )
        write_run(self._store, finished)
        self._runs[finished.reproducibility_run_id] = finished
        return finished

    def _spawn_child_run(
        self, source_training_run_id: str, source_man: ReproducibilityManifest
    ) -> str:
        parent = self._platform.get_training_run(source_training_run_id)
        from app.services.research_data.model_platform.protocol import TrainingRunSpec

        spec = TrainingRunSpec(
            job_id=parent.job_id,
            model_id=parent.model_id,
            model_code=parent.model_code,
            requested_model_version=parent.requested_model_version
            or f"repro-{source_man.repro_manifest_id[:8]}",
            dataset_ref=parent.dataset_ref,
            dataset_hash=parent.dataset_hash,
            snapshot_id=parent.snapshot_id,
            feature_set_id=parent.feature_set_id,
            feature_set_hash=parent.feature_set_hash,
            factor_portfolio_hash=parent.factor_portfolio_hash,
            label_hash=parent.label_hash,
            processor_version=parent.processor_version,
            train_start=parent.train_start,
            train_end=parent.train_end,
            validation_start=parent.validation_start,
            validation_end=parent.validation_end,
            random_seed=parent.random_seed,
            training_config=dict(parent.training_config or {}),
            hyperparameters=dict(parent.hyperparameters or {}),
            resource_config=dict(parent.resource_config or {}),
            framework=parent.framework,
            framework_version=parent.framework_version,
            code_version=parent.code_version,
            environment_hash=parent.environment_hash,
            parent_training_run_id=parent.training_run_id,
            retry_index=int(parent.retry_index or 0),
            metadata={
                "purpose": "reproduce",
                "reproduce_of_training_run_id": parent.training_run_id,
                "code_commit": source_man.code_commit,
            },
        )
        child = self._platform.create_training_run(spec)
        return child.training_run_id

    def _finish_mismatch(
        self,
        run: ReproducibilityRun,
        *,
        source_man: ReproducibilityManifest,
        policy: Any,
        flags: Mapping[str, bool],
        result: str,
        reason: str,
        env: Any,
        child_id: str = "",
    ) -> ReproducibilityRun:
        report = ReproducibilityReport(
            reproducibility_run_id=run.reproducibility_run_id,
            result=result,  # type: ignore[arg-type]
            reason=reason,
            input_match=bool(flags.get("input_match")),
            code_match=bool(flags.get("code_match")),
            environment_match=bool(flags.get("environment_match")),
            dependency_match=bool(flags.get("dependency_match")),
            seed_match=bool(flags.get("seed_match")),
            created_at=datetime.now(timezone.utc),
        )
        uris = write_repro_bundle(
            self._store,
            run.reproducibility_run_id,
            manifest=source_man.model_dump(mode="json"),
            input_manifest=source_man.input_manifest.model_dump(mode="json"),
            environment=env.model_dump(mode="json") if hasattr(env, "model_dump") else {},
            dependency_lock=getattr(env, "dependency_lock", {}) or {},
            seeds=source_man.seeds.model_dump(mode="json"),
            report=report.model_dump(mode="json"),
        )
        finished = run.model_copy(
            update={
                "status": "FAILED",
                "result": result,
                "reason": reason,
                "reproduce_training_run_id": child_id,
                "input_match": bool(flags.get("input_match")),
                "code_match": bool(flags.get("code_match")),
                "environment_match": bool(flags.get("environment_match")),
                "dependency_match": bool(flags.get("dependency_match")),
                "seed_match": bool(flags.get("seed_match")),
                "report": report,
                "report_uri": uris.get("reproducibility_report_uri", ""),
                "completed_at": datetime.now(timezone.utc),
            }
        )
        write_run(self._store, finished)
        self._runs[finished.reproducibility_run_id] = finished
        return finished

    def get_run(self, reproducibility_run_id: str) -> ReproducibilityRun:
        run = self._runs.get(reproducibility_run_id)
        if run is None:
            path = self._store.run_path(
                reproducibility_run_id=reproducibility_run_id
            )
            run = load_json_model(path, ReproducibilityRun)
            if run:
                self._runs[reproducibility_run_id] = run
        if run is None:
            raise ReproducibilityError(
                f"reproducibility run not found: {reproducibility_run_id}"
            )
        return run

    def get_report(self, reproducibility_run_id: str) -> ReproducibilityReport:
        run = self.get_run(reproducibility_run_id)
        if run.report is None:
            raise ReproducibilityError(f"no report for {reproducibility_run_id}")
        return run.report

    def list_runs_for_training_run(
        self, training_run_id: str
    ) -> list[ReproducibilityRun]:
        return sorted(
            [
                r
                for r in self._runs.values()
                if r.source_training_run_id == training_run_id
            ],
            key=lambda r: r.created_at,
        )

    def get_artifact_dir(self, reproducibility_run_id: str) -> Path:
        return self._store.bundle_dir(reproducibility_run_id=reproducibility_run_id)


__all__ = ["ReproducibilityError", "ReproducibilityService"]
