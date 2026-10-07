"""FactorEvaluationPlatformService：9C 对外门面。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.data_query import DataQuery
from app.services.research_data.feature_factor_platform.protocol import FactorBuildIndex
from app.services.research_data.feature_factor_platform.runner import FeatureFactorService
from app.services.research_data.factor_lab.evaluation.artifact_store import (
    EvaluationArtifactStore as LabEvalArtifactStore,
)
from app.services.research_data.factor_lab import (
    FactorEvaluationService,
    FactorGroupEvaluationService,
    FactorMetricsService,
    FactorStabilityService,
)

from .artifact_store import EvaluationArtifactStore
from .hashing import compute_policy_content_hash
from .immutability import (
    EvaluationImmutabilityError,
    assert_run_immutable,
    load_json_model,
)
from .lineage import build_evaluation_lineage
from .orchestrator import EvaluationOrchestrator, EvaluationOrchestratorError
from .pin import pin_evaluation_run
from .policy import EvaluationPolicy
from .policy_presets import get_policy
from .protocol import (
    ENGINE_VERSION,
    EvaluationPlatformInject,
    EvaluationRun,
    EvaluationRunIndex,
    FactorQualityScore,
    LineageNode,
)
from .quality_gate import evaluate_evaluation_run
from .score import compute_quality_score
from .writers import write_quality_score, write_run_index


class FactorEvaluationPlatformError(RuntimeError):
    pass


class _RegistryLike(Protocol):
    def get_feature(self, feature_ref: str) -> Any: ...

    def get_dataset(self, dataset_ref: str) -> Any: ...

    def get_factor_dataset(self, factor_dataset_id: str) -> Any: ...


class _DatasetSvcLike(Protocol):
    def get(self, dataset_ref: str) -> Any: ...


class FactorEvaluationPlatformService:
    """Factor 评价编排（无 mine / promote / capacity）。"""

    def __init__(
        self,
        store: Path | EvaluationArtifactStore | None,
        registry: _RegistryLike,
        *,
        factor_svc: FeatureFactorService | None = None,
        dataset_svc: _DatasetSvcLike | None = None,
        query: DataQuery | None = None,
        canonical_store: CanonicalStore | None = None,
        evaluation_svc: FactorEvaluationService | None = None,
        metrics_svc: FactorMetricsService | None = None,
        groups_svc: FactorGroupEvaluationService | None = None,
        stability_svc: FactorStabilityService | None = None,
    ) -> None:
        if isinstance(store, EvaluationArtifactStore):
            self._store = store
        elif isinstance(store, Path):
            self._store = EvaluationArtifactStore(root=store)
        else:
            self._store = EvaluationArtifactStore()
        self._registry = registry
        self._factor_svc = factor_svc
        self._dataset_svc = dataset_svc
        self._canonical = canonical_store
        self._query = query
        if evaluation_svc is None:
            if query is None or canonical_store is None:
                raise FactorEvaluationPlatformError(
                    "query and canonical_store required when evaluation_svc omitted"
                )
            evaluation_svc = FactorEvaluationService(
                query,
                registry,  # type: ignore[arg-type]
                canonical_store,
                artifact_store=LabEvalArtifactStore(
                    root=Path(store) if isinstance(store, Path) else None
                ),
            )
        self._orchestrator = EvaluationOrchestrator(
            canonical_store,  # type: ignore[arg-type]
            registry,  # type: ignore[arg-type]
            evaluation_svc=evaluation_svc,
            metrics_svc=metrics_svc,
            groups_svc=groups_svc,
            stability_svc=stability_svc,
        )

    @property
    def engine_version(self) -> str:
        return ENGINE_VERSION

    def run_evaluation(
        self,
        factor_ref: str,
        dataset_ref: str,
        *,
        policy_id: str = "default_equity_factor_v1",
        window: tuple[str, str] | None = None,
        layout: str = "long",
        inject: Mapping[str, Any] | EvaluationPlatformInject | None = None,
    ) -> EvaluationRun:
        inj = _coerce_inject(inject)
        policy = self._resolve_policy(policy_id, inj)
        policy_hash = compute_policy_content_hash(policy)

        start_date, end_date = self._resolve_window(window)
        handle = self._dataset_svc.get(dataset_ref) if self._dataset_svc else self._registry.get_dataset(dataset_ref)  # type: ignore[union-attr]
        build_index = self._resolve_build_index(
            factor_ref,
            dataset_ref,
            handle,
            layout=layout,
            start_date=start_date,
            end_date=end_date,
            inj=inj,
        )
        feature = self._registry.get_feature(factor_ref)
        gate = evaluate_evaluation_run(
            feature=feature,
            handle=handle,
            build_index=build_index,
            registry=self._registry,
            inject=inject,
        )

        run_hash_preview = self._preview_run_hash(
            build_index, handle, policy_hash, start_date, end_date
        )
        existing = self.get_by_hash(run_hash_preview)
        if existing is not None:
            if existing.status == "SUCCESS":
                return existing
            if existing.status == "BLOCKED" and gate.verdict != "PASS":
                return existing

        if gate.verdict != "PASS":
            idx, run = pin_evaluation_run(
                factor_ref=factor_ref,
                dataset_ref=dataset_ref,
                build_index=build_index,
                handle=handle,
                policy_id=policy.policy_id,
                policy_content_hash=policy_hash,
                policy_version=policy.version,
                start_date=start_date,
                end_date=end_date,
                status="BLOCKED",
                gate_verdict="BLOCKED",
                gate_reasons=gate.reasons,
            )
            self._persist_run(idx, inj)
            return run

        factor_ds = self._registry.get_factor_dataset(build_index.factor_dataset_id)
        lab_meta = dict(inj.lab_metadata or {}) if inj else {}
        lab_meta.setdefault("factor_dataset_id", build_index.factor_dataset_id)

        try:
            artifacts = self._orchestrator.run(
                policy,
                build_index=build_index,
                handle=handle,
                factor_ds=factor_ds,
                start_date=start_date,
                end_date=end_date,
                lab_metadata=lab_meta,
            )
        except EvaluationOrchestratorError as exc:
            raise FactorEvaluationPlatformError(str(exc)) from exc

        idx, run = pin_evaluation_run(
            factor_ref=factor_ref,
            dataset_ref=dataset_ref,
            build_index=build_index,
            handle=handle,
            policy_id=policy.policy_id,
            policy_content_hash=policy_hash,
            policy_version=policy.version,
            start_date=start_date,
            end_date=end_date,
            status="SUCCESS",
            gate_verdict="PASS",
            evaluation_hash=artifacts.evaluation_hash,
            metric_hash=artifacts.metric_hash,
            group_evaluation_hash=artifacts.group_evaluation_hash,
            stability_hash=artifacts.stability_hash,
            resolved_direction=artifacts.resolved_direction,
        )

        score = compute_quality_score(
            evaluation_id=idx.evaluation_id,
            run_content_hash=idx.run_content_hash,
            raw_metrics=artifacts.raw_metrics,
            primary_horizon=policy.return_spec.horizons[0],
        )
        wr = write_quality_score(self._store, score)
        idx = idx.model_copy(update={"quality_score_uri": wr.path})
        run = run.model_copy(update={"quality_score_uri": wr.path})

        self._persist_run(idx, inj)
        self._persist_score(score)
        return run

    def get_run(self, evaluation_id: str) -> EvaluationRun:
        for path in self._store.list_run_index_paths():
            idx = load_json_model(path, EvaluationRunIndex)
            if idx and idx.evaluation_id == evaluation_id:
                return self._index_to_run(idx)
        stored = self._load_run_from_registry(evaluation_id)
        if stored is None:
            raise FactorEvaluationPlatformError(f"evaluation run not found: {evaluation_id}")
        return stored

    def get_by_hash(self, run_content_hash: str) -> EvaluationRun | None:
        path = self._store.run_index_path(run_content_hash=run_content_hash)
        idx = load_json_model(path, EvaluationRunIndex)
        if idx is None:
            return None
        return self._index_to_run(idx)

    def list_runs(self, factor_hash: str | None = None) -> list[EvaluationRun]:
        runs: list[EvaluationRun] = []
        for path in self._store.list_run_index_paths():
            idx = load_json_model(path, EvaluationRunIndex)
            if idx is None:
                continue
            if factor_hash and idx.factor_hash != factor_hash:
                continue
            runs.append(self._index_to_run(idx))
        runs.sort(key=lambda r: r.published_at)
        return runs

    def get_quality_score(self, evaluation_id: str) -> FactorQualityScore:
        path = self._store.quality_score_path(evaluation_id=evaluation_id)
        if not path.is_file():
            raise FactorEvaluationPlatformError(
                f"quality score missing for {evaluation_id}"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return FactorQualityScore.model_validate(data)

    def get_lineage(self, evaluation_id: str) -> LineageNode:
        run = self.get_run(evaluation_id)
        idx_path = self._store.run_index_path(run_content_hash=run.run_content_hash)
        idx = load_json_model(idx_path, EvaluationRunIndex)
        if idx is None:
            raise FactorEvaluationPlatformError(f"run index missing for {evaluation_id}")
        return build_evaluation_lineage(self._registry, idx)

    def _resolve_policy(
        self, policy_id: str, inj: EvaluationPlatformInject | None
    ) -> EvaluationPolicy:
        policy = get_policy(policy_id)
        if inj and inj.policy_overrides:
            policy = policy.model_copy(update=dict(inj.policy_overrides))
        return policy

    def _resolve_window(self, window: tuple[str, str] | None) -> tuple[str, str]:
        if window is None:
            raise FactorEvaluationPlatformError("window (start_date, end_date) is required")
        a, b = window
        if not a or not b or a > b:
            raise FactorEvaluationPlatformError("invalid evaluation window")
        return a, b

    def _resolve_build_index(
        self,
        factor_ref: str,
        dataset_ref: str,
        handle: Any,
        *,
        layout: str,
        start_date: str,
        end_date: str,
        inj: EvaluationPlatformInject | None,
    ) -> FactorBuildIndex:
        if inj and inj.build_index_payload:
            return FactorBuildIndex.model_validate(inj.build_index_payload)
        if self._factor_svc is None:
            raise FactorEvaluationPlatformError(
                "factor_svc required to resolve FactorBuildIndex"
            )
        return self._factor_svc.get_factor_build_index(
            factor_ref,
            handle.dataset_hash,
            layout=layout,
            start_date=start_date,
            end_date=end_date,
        )

    def _preview_run_hash(
        self,
        build_index: FactorBuildIndex,
        handle: Any,
        policy_hash: str,
        start_date: str,
        end_date: str,
    ) -> str:
        from .hashing import compute_run_content_hash

        return compute_run_content_hash(
            factor_hash=build_index.factor_hash,
            dataset_hash=handle.dataset_hash,
            factor_dataset_id=build_index.factor_dataset_id,
            policy_content_hash=policy_hash,
            start_date=start_date,
            end_date=end_date,
            layout=build_index.layout,
        )

    def _persist_run(
        self,
        idx: EvaluationRunIndex,
        inj: EvaluationPlatformInject | None,
    ) -> None:
        path = self._store.run_index_path(run_content_hash=idx.run_content_hash)
        existing = load_json_model(path, EvaluationRunIndex)
        if existing is not None:
            if existing.status == "BLOCKED" and idx.status == "SUCCESS":
                write_run_index(self._store, idx)
                self._persist_run_registry(idx)
                return
            if inj and inj.skip_immutability:
                pass
            else:
                try:
                    assert_run_immutable(existing, idx)
                except EvaluationImmutabilityError as exc:
                    raise FactorEvaluationPlatformError(str(exc)) from exc
                return
        write_run_index(self._store, idx)
        self._persist_run_registry(idx)

    def _persist_run_registry(self, idx: EvaluationRunIndex) -> None:
        if not hasattr(self._registry, "_read"):
            return
        with self._registry._lock:  # type: ignore[attr-defined]
            data = self._registry._read()
            data.setdefault("evaluation_runs", {})[idx.evaluation_id] = idx.model_dump(
                mode="json"
            )
            self._registry._write(data)

    def _persist_score(self, score: FactorQualityScore) -> None:
        if not hasattr(self._registry, "_read"):
            return
        with self._registry._lock:  # type: ignore[attr-defined]
            data = self._registry._read()
            data.setdefault("evaluation_quality_scores", {})[score.evaluation_id] = (
                score.model_dump(mode="json")
            )
            self._registry._write(data)

    def _load_run_from_registry(self, evaluation_id: str) -> EvaluationRun | None:
        if not hasattr(self._registry, "_read"):
            return None
        data = self._registry._read()
        raw = (data.get("evaluation_runs") or {}).get(evaluation_id)
        if not raw:
            return None
        idx = EvaluationRunIndex.model_validate(raw)
        return self._index_to_run(idx)

    @staticmethod
    def _index_to_run(idx: EvaluationRunIndex) -> EvaluationRun:
        return EvaluationRun(
            evaluation_id=idx.evaluation_id,
            run_content_hash=idx.run_content_hash,
            status=idx.status,
            factor_ref=idx.factor_ref,
            factor_hash=idx.factor_hash,
            dataset_ref=idx.dataset_ref,
            dataset_hash=idx.dataset_hash,
            factor_dataset_id=idx.factor_dataset_id,
            policy_id=idx.policy_id,
            policy_content_hash=idx.policy_content_hash,
            evaluation_policy_version=idx.evaluation_policy_version,
            start_date=idx.start_date,
            end_date=idx.end_date,
            evaluation_hash=idx.evaluation_hash,
            metric_hash=idx.metric_hash,
            group_evaluation_hash=idx.group_evaluation_hash,
            stability_hash=idx.stability_hash,
            resolved_direction=idx.resolved_direction,
            gate_verdict=idx.gate_verdict,
            gate_reasons=list(idx.gate_reasons),
            quality_score_uri=idx.quality_score_uri,
            published_at=idx.published_at,
            metadata=dict(idx.metadata),
        )


def _coerce_inject(
    inject: Mapping[str, Any] | EvaluationPlatformInject | None,
) -> EvaluationPlatformInject | None:
    if inject is None:
        return None
    if isinstance(inject, EvaluationPlatformInject):
        return inject
    section = inject.get("evaluation_platform") if isinstance(inject, dict) else None
    if isinstance(section, dict):
        return EvaluationPlatformInject.model_validate(section)
    if isinstance(inject, dict) and any(
        k in inject for k in EvaluationPlatformInject.model_fields
    ):
        return EvaluationPlatformInject.model_validate(inject)
    return None


__all__ = [
    "FactorEvaluationPlatformError",
    "FactorEvaluationPlatformService",
]
