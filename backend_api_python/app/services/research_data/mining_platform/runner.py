"""FactorMiningService：9D 对外门面。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol

from app.services.research_data.contracts import FeatureDefinition
from app.services.research_data.evaluation_platform.policy_presets import get_policy as get_eval_policy
from app.services.research_data.feature_factor_platform.runner import FeatureFactorService
from app.services.research_data.evaluation_platform.runner import FactorEvaluationPlatformService

from .artifact_store import MiningArtifactStore
from .feature_universe import resolve_feature_universe
from .hashing import compute_mining_policy_content_hash
from .immutability import (
    MiningImmutabilityError,
    assert_run_immutable,
    load_json_model,
)
from .orchestrator import MiningOrchestrator, MiningOrchestratorError
from .pin import pin_mining_run
from .policy import MiningPolicy
from .policy_presets import get_policy
from .protocol import (
    ENGINE_VERSION,
    MiningJob,
    MiningPlatformInject,
    MiningRun,
    MiningRunIndex,
    FactorCandidate,
)
from .writers import write_candidate, write_mining_score, write_run_index


class FactorMiningError(RuntimeError):
    pass


class _RegistryLike(Protocol):
    def get_dataset(self, dataset_ref: str) -> Any: ...


class _DatasetSvcLike(Protocol):
    def get(self, dataset_ref: str) -> Any: ...


class FactorMiningService:
    """Factor 挖掘（无 GP / auto APPROVED / promote_strategy）。"""

    def __init__(
        self,
        store: Path | MiningArtifactStore | None,
        registry: _RegistryLike,
        *,
        factor_svc: FeatureFactorService | None = None,
        eval_svc: FactorEvaluationPlatformService | None = None,
        dataset_svc: _DatasetSvcLike | None = None,
    ) -> None:
        if isinstance(store, MiningArtifactStore):
            self._store = store
        elif isinstance(store, Path):
            self._store = MiningArtifactStore(root=store)
        else:
            self._store = MiningArtifactStore()
        self._registry = registry
        self._factor_svc = factor_svc
        self._eval_svc = eval_svc
        self._dataset_svc = dataset_svc
        self._orchestrator = MiningOrchestrator(
            factor_svc=factor_svc,
            eval_svc=eval_svc,
        )

    @property
    def engine_version(self) -> str:
        return ENGINE_VERSION

    def run_mining(
        self,
        job: MiningJob | dict[str, Any],
        *,
        inject: Mapping[str, Any] | MiningPlatformInject | None = None,
    ) -> MiningRun:
        inj = _coerce_inject(inject)
        j = MiningJob.model_validate(job) if isinstance(job, dict) else job
        policy = self._resolve_policy(j.mining_policy_id, inj)
        if policy.random_seed_required and j.random_seed is None:
            raise FactorMiningError("random_seed is required")

        handle = (
            self._dataset_svc.get(j.dataset_ref)
            if self._dataset_svc
            else self._registry.get_dataset(j.dataset_ref)
        )
        universe = resolve_feature_universe(
            feature_set_ref=j.feature_set_ref,
            feature_columns=j.feature_columns or None,
            factor_svc=self._factor_svc,
        )
        mining_hash = self._preview_run_hash(
            handle.dataset_hash,
            universe.feature_set_hash,
            policy,
            j.evaluation_policy_id,
            j.random_seed,
        )
        existing = self.get_by_hash(mining_hash)
        if existing is not None and existing.status == "COMPLETED":
            return existing

        eval_pol = get_eval_policy(j.evaluation_policy_id)
        policy_hash = compute_mining_policy_content_hash(policy)

        idx_preview, run_preview = pin_mining_run(
            dataset_ref=j.dataset_ref,
            handle=handle,
            feature_set_hash=universe.feature_set_hash,
            mining_policy_id=policy.policy_id,
            mining_policy_content_hash=policy_hash,
            evaluation_policy_id=j.evaluation_policy_id,
            evaluation_policy_version=eval_pol.version,
            random_seed=j.random_seed,
            status="RUNNING",
        )

        try:
            result = self._orchestrator.run(
                j,
                policy=policy,
                universe=universe,
                handle=handle,
                mining_run_id=idx_preview.mining_run_id,
                inject=inj,
            )
        except MiningOrchestratorError as exc:
            raise FactorMiningError(str(exc)) from exc

        idx, run = pin_mining_run(
            dataset_ref=j.dataset_ref,
            handle=handle,
            feature_set_hash=universe.feature_set_hash,
            mining_policy_id=policy.policy_id,
            mining_policy_content_hash=policy_hash,
            evaluation_policy_id=j.evaluation_policy_id,
            evaluation_policy_version=eval_pol.version,
            random_seed=j.random_seed,
            status=result.stats.status,
            total_candidates_generated=result.stats.generated,
            total_candidates_screened=result.stats.screened,
            total_candidates_tested=result.stats.tested,
            total_survivors=result.stats.survivors,
            candidates=result.candidates,
            mining_run_id=idx_preview.mining_run_id,
        )
        self._persist_run(idx, inj)
        for c in result.candidates:
            write_candidate(self._store, c)
        for sc in result.scores:
            write_mining_score(self._store, sc)
        return run

    def get_run(self, mining_run_id: str) -> MiningRun:
        idx = self._find_run_index(mining_run_id)
        if idx is None:
            raise FactorMiningError(f"mining run not found: {mining_run_id}")
        return self._index_to_run(idx)

    def get_by_hash(self, mining_run_hash: str) -> MiningRun | None:
        path = self._store.run_index_path(mining_run_hash=mining_run_hash)
        idx = load_json_model(path, MiningRunIndex)
        if idx is None:
            return None
        return self._index_to_run(idx)

    def list_candidates(self, mining_run_id: str) -> list[FactorCandidate]:
        idx = self._find_run_index(mining_run_id)
        if idx is None:
            return []
        out: list[FactorCandidate] = []
        for cid in idx.candidate_ids:
            cp = self._store.candidate_path(
                mining_run_id=mining_run_id, candidate_id=cid
            )
            cand = load_json_model(cp, FactorCandidate)
            if cand:
                out.append(cand)
        return out

    def _find_run_index(self, mining_run_id: str) -> MiningRunIndex | None:
        for path in self._store.list_run_index_paths():
            loaded = load_json_model(path, MiningRunIndex)
            if loaded and loaded.mining_run_id == mining_run_id:
                return loaded
        if hasattr(self._registry, "_read"):
            data = self._registry._read()
            raw = (data.get("mining_runs") or {}).get(mining_run_id)
            if raw:
                return MiningRunIndex.model_validate(raw)
        return None

    def promote_candidate_to_draft(self, candidate_id: str) -> FeatureDefinition:
        """显式晋升：仅 DRAFT lifecycle，非 APPROVED。"""
        cand = self._find_candidate(candidate_id)
        if not cand.factor_ref:
            raise FactorMiningError(f"candidate {candidate_id} has no factor_ref")
        if self._factor_svc is None:
            raise FactorMiningError("factor_svc required for promote_candidate_to_draft")
        reg = self._factor_svc._registry  # type: ignore[attr-defined]
        try:
            feat = reg.get_feature(cand.factor_ref)
        except KeyError:
            code, version = cand.factor_ref.split("@", 1)
            feat = FeatureDefinition(
                code=code,
                version=version,
                name=f"Mined {cand.dsl_expression[:48]}",
                expression=cand.dsl_expression,
                factor_type="TECHNICAL",
                computation_engine="quantdinger",
                dependencies=["market:CNStock"],
                information_policy="NON_PIT",
                definition={
                    "lifecycle_status": "DRAFT",
                    "mined": True,
                    "expression_hash": cand.expression_hash,
                    "promoted_from_mining": candidate_id,
                },
            )
            return self._factor_svc.register_factor(feat)
        if feat.definition.get("lifecycle_status") != "DRAFT":
            raise FactorMiningError(
                f"candidate {candidate_id} factor is not DRAFT lifecycle"
            )
        return feat

    def _find_candidate(self, candidate_id: str) -> FactorCandidate:
        for path in self._store.list_run_index_paths():
            idx = load_json_model(path, MiningRunIndex)
            if not idx or candidate_id not in idx.candidate_ids:
                continue
            cp = self._store.candidate_path(
                mining_run_id=idx.mining_run_id, candidate_id=candidate_id
            )
            cand = load_json_model(cp, FactorCandidate)
            if cand:
                return cand
        raise FactorMiningError(f"candidate not found: {candidate_id}")

    def _resolve_policy(
        self, policy_id: str, inj: MiningPlatformInject | None
    ) -> MiningPolicy:
        policy = get_policy(policy_id)
        if inj and inj.policy_overrides:
            policy = policy.model_copy(update=dict(inj.policy_overrides))
        return policy

    def _preview_run_hash(
        self,
        dataset_hash: str,
        feature_set_hash: str,
        policy: MiningPolicy,
        evaluation_policy_id: str,
        random_seed: int,
    ) -> str:
        from .hashing import compute_mining_run_hash

        eval_pol = get_eval_policy(evaluation_policy_id)
        return compute_mining_run_hash(
            dataset_hash=dataset_hash,
            feature_set_hash=feature_set_hash,
            mining_policy_content_hash=compute_mining_policy_content_hash(policy),
            evaluation_policy_version=eval_pol.version,
            random_seed=random_seed,
        )

    def _persist_run(
        self,
        idx: MiningRunIndex,
        inj: MiningPlatformInject | None,
    ) -> None:
        path = self._store.run_index_path(mining_run_hash=idx.mining_run_hash)
        existing = load_json_model(path, MiningRunIndex)
        if existing is not None:
            if inj and inj.skip_immutability:
                pass
            else:
                try:
                    assert_run_immutable(existing, idx)
                except MiningImmutabilityError as exc:
                    raise FactorMiningError(str(exc)) from exc
                if existing.status == "COMPLETED":
                    return
        write_run_index(self._store, idx)
        self._persist_run_registry(idx)

    def _persist_run_registry(self, idx: MiningRunIndex) -> None:
        if not hasattr(self._registry, "_read"):
            return
        with self._registry._lock:  # type: ignore[attr-defined]
            data = self._registry._read()
            data.setdefault("mining_runs", {})[idx.mining_run_id] = idx.model_dump(
                mode="json"
            )
            self._registry._write(data)

    def _index_to_run(self, idx: MiningRunIndex) -> MiningRun:
        cands = self.list_candidates(idx.mining_run_id)
        return MiningRun(
            mining_run_id=idx.mining_run_id,
            mining_run_hash=idx.mining_run_hash,
            status=idx.status,
            dataset_ref=idx.dataset_ref,
            dataset_hash=idx.dataset_hash,
            feature_set_hash=idx.feature_set_hash,
            mining_policy_id=idx.mining_policy_id,
            mining_policy_content_hash=idx.mining_policy_content_hash,
            evaluation_policy_id=idx.evaluation_policy_id,
            evaluation_policy_version=idx.evaluation_policy_version,
            random_seed=idx.random_seed,
            total_candidates_generated=idx.total_candidates_generated,
            total_candidates_screened=idx.total_candidates_screened,
            total_candidates_tested=idx.total_candidates_tested,
            total_survivors=idx.total_survivors,
            selection_bias_warning=idx.selection_bias_warning,
            candidates=cands,
            published_at=idx.published_at,
            metadata=dict(idx.metadata),
        )


def _coerce_inject(
    inject: Mapping[str, Any] | MiningPlatformInject | None,
) -> MiningPlatformInject | None:
    if inject is None:
        return None
    if isinstance(inject, MiningPlatformInject):
        return inject
    section = inject.get("mining_platform") if isinstance(inject, dict) else None
    if isinstance(section, dict):
        return MiningPlatformInject.model_validate(section)
    if isinstance(inject, dict) and any(
        k in inject for k in MiningPlatformInject.model_fields
    ):
        return MiningPlatformInject.model_validate(inject)
    return None


__all__ = ["FactorMiningError", "FactorMiningService"]
