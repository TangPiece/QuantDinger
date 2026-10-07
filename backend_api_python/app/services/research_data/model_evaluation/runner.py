"""ModelEvaluationService：评估编排（不接 ACTIVE/LIVE）。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .artifact_store import ModelEvaluationArtifactStore
from .immutability import (
    ModelEvaluationImmutabilityError,
    assert_run_immutable,
    load_json_model,
)
from .metrics import (
    build_metric_list,
    compute_predictive_metrics,
    compute_ranking_at_k,
    compute_stability_profile,
    summarize_layer_statuses,
)
from .pin import pin_evaluation_run
from .policy import resolve_policy
from .predictor import PredictorError, build_prediction_rows
from .protocol import (
    ENGINE_VERSION,
    ModelEvaluationInject,
    ModelEvaluationRequest,
    ModelEvaluationResult,
    ModelEvaluationRun,
)
from .quality_gate import check_prediction_panel, evaluate_quality_gate
from .writers import write_evaluation_bundle, write_run


class ModelEvaluationError(RuntimeError):
    pass


def _coerce_inject(
    inject: Mapping[str, Any] | ModelEvaluationInject | None,
) -> ModelEvaluationInject | None:
    if inject is None:
        return None
    if isinstance(inject, ModelEvaluationInject):
        return inject
    section = inject.get("model_evaluation") if isinstance(inject, dict) else None
    if isinstance(section, dict):
        return ModelEvaluationInject.model_validate(section)
    if isinstance(inject, dict) and any(
        k in inject for k in ModelEvaluationInject.model_fields
    ):
        return ModelEvaluationInject.model_validate(inject)
    return None


class ModelEvaluationService:
    """独立于 ModelPlatformService；无 evaluate_model / auto ACTIVE。"""

    def __init__(
        self,
        store: Path | ModelEvaluationArtifactStore | None = None,
        *,
        model_platform: Any | None = None,
    ) -> None:
        if isinstance(store, ModelEvaluationArtifactStore):
            self._store = store
        elif isinstance(store, Path):
            self._store = ModelEvaluationArtifactStore(root=store)
        else:
            self._store = ModelEvaluationArtifactStore()
        self._model_platform = model_platform
        self._runs: dict[str, ModelEvaluationRun] = {}
        self._by_hash: dict[str, str] = {}
        self._hydrate()

    @property
    def engine_version(self) -> str:
        return ENGINE_VERSION

    def _hydrate(self) -> None:
        for path in self._store.list_run_paths():
            run = load_json_model(path, ModelEvaluationRun)
            if run:
                self._runs[run.evaluation_run_id] = run
                self._by_hash[run.run_content_hash] = run.evaluation_run_id

    def run_evaluation(
        self,
        request: ModelEvaluationRequest | dict[str, Any],
        *,
        inject: Mapping[str, Any] | ModelEvaluationInject | None = None,
    ) -> ModelEvaluationRun:
        if isinstance(request, dict):
            request = ModelEvaluationRequest.model_validate(request)
        inj = _coerce_inject(inject)
        policy = resolve_policy(request.policy_code)
        draft = pin_evaluation_run(request)

        existing_id = self._by_hash.get(draft.run_content_hash)
        if existing_id and not (inj and inj.skip_immutability):
            existing = self.get_run(existing_id)
            try:
                assert_run_immutable(existing, draft)
                return existing
            except ModelEvaluationImmutabilityError:
                return existing

        version_lifecycle = ""
        artifact_status = ""
        if self._model_platform is not None:
            try:
                ver = self._model_platform.get_version(request.model_version_id)
                version_lifecycle = ver.lifecycle
                if ver.artifact_id:
                    art = self._model_platform.get_artifact(ver.artifact_id)
                    artifact_status = art.status
                if inj and inj.mark_evaluating and ver.lifecycle == "TRAINED":
                    try:
                        self._model_platform.transition(
                            ver.model_version_id, "EVALUATING"
                        )
                    except Exception:
                        pass
            except Exception as exc:
                # version missing → gate will block
                version_lifecycle = version_lifecycle or ""
                draft = draft.model_copy(
                    update={
                        "metadata": {
                            **dict(draft.metadata or {}),
                            "version_lookup_error": str(exc),
                        }
                    }
                )

        if inj and inj.skip_artifact_check:
            artifact_status = artifact_status or "AVAILABLE"
            version_lifecycle = version_lifecycle or "TRAINED"

        now = datetime.now(timezone.utc)
        run = draft.model_copy(
            update={"status": "RUNNING", "started_at": now}
        )
        write_run(self._store, run)
        self._runs[run.evaluation_run_id] = run

        gate = evaluate_quality_gate(
            request,
            policy=policy,
            version_lifecycle=version_lifecycle or "TRAINED",
            artifact_status=artifact_status or ("AVAILABLE" if inj and inj.predictions else ""),
            inject=inj,
        )
        if gate.verdict == "BLOCKED":
            result = ModelEvaluationResult(
                evaluation_run_id=run.evaluation_run_id,
                quality_status="BLOCKED",
                predictive_status="BLOCKED",
                stability_status="BLOCKED",
                ranking_status="BLOCKED",
                overall_status="BLOCKED",
                created_at=datetime.now(timezone.utc),
            )
            finished = run.model_copy(
                update={
                    "status": "BLOCKED",
                    "gate_reasons": gate.reasons,
                    "finished_at": datetime.now(timezone.utc),
                    "result": result,
                }
            )
            write_run(self._store, finished)
            self._runs[finished.evaluation_run_id] = finished
            self._by_hash[finished.run_content_hash] = finished.evaluation_run_id
            return finished

        try:
            rows = build_prediction_rows(
                request, inject=inj, model_platform=self._model_platform
            )
        except PredictorError as exc:
            result = ModelEvaluationResult(
                evaluation_run_id=run.evaluation_run_id,
                quality_status="FAIL",
                overall_status="FAIL",
                created_at=datetime.now(timezone.utc),
                raw_metrics={"error": str(exc)},
            )
            finished = run.model_copy(
                update={
                    "status": "FAILED",
                    "gate_reasons": [str(exc)],
                    "finished_at": datetime.now(timezone.utc),
                    "result": result,
                }
            )
            write_run(self._store, finished)
            self._runs[finished.evaluation_run_id] = finished
            self._by_hash[finished.run_content_hash] = finished.evaluation_run_id
            return finished

        pred_issues = check_prediction_panel(rows)
        if pred_issues:
            result = ModelEvaluationResult(
                evaluation_run_id=run.evaluation_run_id,
                quality_status="FAIL",
                overall_status="FAIL",
                created_at=datetime.now(timezone.utc),
                raw_metrics={"prediction_issues": pred_issues},
            )
            finished = run.model_copy(
                update={
                    "status": "FAILED",
                    "gate_reasons": pred_issues,
                    "finished_at": datetime.now(timezone.utc),
                    "result": result,
                }
            )
            write_run(self._store, finished)
            self._runs[finished.evaluation_run_id] = finished
            self._by_hash[finished.run_content_hash] = finished.evaluation_run_id
            return finished

        predictive = compute_predictive_metrics(rows, policy=policy)
        ranking = compute_ranking_at_k(rows, ks=list(policy.ranking_ks))
        stability = compute_stability_profile(
            rows, min_cs=policy.min_cross_section
        )
        layers = summarize_layer_statuses(
            quality="PASS",
            predictive=predictive,
            ranking=ranking,
            stability=stability,
        )
        raw = {
            "predictive": predictive,
            "ranking": ranking,
            "stability": stability,
            "feature_importance": {"status": "SKIPPED"},
        }
        result = ModelEvaluationResult(
            evaluation_run_id=run.evaluation_run_id,
            quality_status=layers["quality_status"],
            predictive_status=layers["predictive_status"],
            stability_status=layers["stability_status"],
            ranking_status=layers["ranking_status"],
            overall_status=layers["overall_status"],
            metrics=build_metric_list(predictive),
            raw_metrics=raw,
            created_at=datetime.now(timezone.utc),
        )
        uris = write_evaluation_bundle(
            self._store,
            run.evaluation_run_id,
            metrics=raw,
            predictions=rows,
            ranking=ranking,
            stability=stability,
            feature_importance={"status": "SKIPPED"},
            manifest={
                "evaluation_run_id": run.evaluation_run_id,
                "model_version_id": run.model_version_id,
                "evaluation_dataset_hash": run.evaluation_dataset_hash,
                "policy": run.evaluation_policy_version,
                "run_content_hash": run.run_content_hash,
            },
        )
        finished = run.model_copy(
            update={
                "status": "SUCCEEDED",
                "finished_at": datetime.now(timezone.utc),
                "metrics_uri": uris.get("metrics_uri", ""),
                "prediction_uri": uris.get("prediction_uri", ""),
                "result": result,
                "metadata": {
                    **dict(run.metadata or {}),
                    "artifact_uris": uris,
                },
            }
        )
        write_run(self._store, finished)
        self._runs[finished.evaluation_run_id] = finished
        self._by_hash[finished.run_content_hash] = finished.evaluation_run_id
        return finished

    def get_run(self, evaluation_run_id: str) -> ModelEvaluationRun:
        run = self._runs.get(evaluation_run_id)
        if run is None:
            path = self._store.run_path(evaluation_run_id=evaluation_run_id)
            run = load_json_model(path, ModelEvaluationRun)
            if run:
                self._runs[evaluation_run_id] = run
        if run is None:
            raise ModelEvaluationError(f"evaluation run not found: {evaluation_run_id}")
        return run

    def list_runs_for_version(self, model_version_id: str) -> list[ModelEvaluationRun]:
        return [
            r
            for r in self._runs.values()
            if r.model_version_id == model_version_id
        ]

    def get_result(self, evaluation_run_id: str) -> ModelEvaluationResult:
        run = self.get_run(evaluation_run_id)
        if run.result is None:
            raise ModelEvaluationError(f"no result for {evaluation_run_id}")
        return run.result

    def get_metrics_summary(self, evaluation_run_id: str) -> dict[str, Any]:
        result = self.get_result(evaluation_run_id)
        return dict(result.raw_metrics or {})

    def get_artifact_dir(self, evaluation_run_id: str) -> Path:
        return self._store.bundle_dir(evaluation_run_id=evaluation_run_id)


__all__ = ["ModelEvaluationError", "ModelEvaluationService"]
