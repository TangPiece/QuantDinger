"""FactorLibraryService：9E 对外门面。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from app.services.research_data.evaluation_platform.runner import FactorEvaluationPlatformService
from app.services.research_data.feature_factor_platform.feature_set import FeatureSetDefinition
from app.services.research_data.feature_factor_platform.runner import FeatureFactorService
from app.services.research_data.mining_platform.runner import FactorMiningService

from .artifact_store import LibraryArtifactStore
from .bridge_featureset import from_collection, from_portfolio
from .catalog import LibraryCatalog
from .cluster import build_factor_cluster
from .collection import build_collection
from .immutability import (
    LibraryImmutabilityError,
    assert_entry_immutable,
    load_json_model,
)
from .lifecycle import (
    LibraryLifecycleError,
    assert_transition,
    can_activate,
    can_deprecate,
    can_retire,
)
from .lineage import list_usages
from .pin import pin_library_entry
from .portfolio_spec import build_portfolio_spec
from .promotion import PromotionGateError, assert_promotion_pass, evaluate_promotion_gate
from .protocol import (
    ENGINE_VERSION,
    FactorCluster,
    FactorClusterPolicy,
    FactorCollection,
    FactorLibraryEntry,
    FactorLibraryInject,
    FactorPortfolioSpec,
    FactorSearchQuery,
    SimilarFactorHit,
    WeightMethod,
)
from .search import search_entries
from .similarity import similar_factors
from .taxonomy import normalize_category, normalize_tags
from .weights import resolve_portfolio_weights
from .writers import write_cluster, write_collection, write_entry, write_portfolio


class FactorLibraryError(RuntimeError):
    pass


class _RegistryLike(Protocol):
    def get_feature(self, feature_ref: str) -> Any: ...


def _coerce_inject(
    inject: Mapping[str, Any] | FactorLibraryInject | None,
) -> FactorLibraryInject | None:
    if inject is None:
        return None
    if isinstance(inject, FactorLibraryInject):
        return inject
    section = inject.get("factor_library_platform") if isinstance(inject, dict) else None
    if isinstance(section, dict):
        return FactorLibraryInject.model_validate(section)
    if isinstance(inject, dict) and any(k in inject for k in FactorLibraryInject.model_fields):
        return FactorLibraryInject.model_validate(inject)
    return None


class FactorLibraryService:
    """Factor Library（无 auto LIVE / MV optimizer）。"""

    def __init__(
        self,
        store: Path | LibraryArtifactStore | None,
        registry: _RegistryLike,
        *,
        factor_svc: FeatureFactorService | None = None,
        eval_svc: FactorEvaluationPlatformService | None = None,
        mining_svc: FactorMiningService | None = None,
    ) -> None:
        if isinstance(store, LibraryArtifactStore):
            self._store = store
        elif isinstance(store, Path):
            self._store = LibraryArtifactStore(root=store)
        else:
            self._store = LibraryArtifactStore()
        self._registry = registry
        self._factor_svc = factor_svc
        self._eval_svc = eval_svc
        self._mining_svc = mining_svc
        self._catalog = LibraryCatalog()
        self._collections: dict[str, FactorCollection] = {}
        self._portfolios: dict[str, FactorPortfolioSpec] = {}
        self._clusters: dict[str, FactorCluster] = {}
        self._hydrate_from_disk()

    @property
    def engine_version(self) -> str:
        return ENGINE_VERSION

    def _hydrate_from_disk(self) -> None:
        for path in self._store.list_entry_paths():
            entry = load_json_model(path, FactorLibraryEntry)
            if entry:
                self._catalog.upsert(entry)

    def register_entry_from_factor(
        self,
        factor_ref: str,
        *,
        evaluation_id: str,
        category: str = "OTHER",
        tags: list[str] | None = None,
        inject: Mapping[str, Any] | FactorLibraryInject | None = None,
    ) -> FactorLibraryEntry:
        inj = _coerce_inject(inject)
        if self._eval_svc is None:
            raise FactorLibraryError("eval_svc required")
        run = self._eval_svc.get_run(evaluation_id)
        if run.factor_ref != factor_ref:
            raise FactorLibraryError("evaluation factor_ref mismatch")
        score = None
        try:
            score = self._eval_svc.get_quality_score(evaluation_id)
        except Exception:
            pass
        gate = evaluate_promotion_gate(
            evaluation_run=run,
            quality_score=score,
            inject=inj,
        )
        assert_promotion_pass(gate)
        entry = pin_library_entry(
            factor_ref=factor_ref,
            factor_hash=run.factor_hash,
            evaluation_id=evaluation_id,
            dataset_ref=run.dataset_ref,
            dataset_hash=run.dataset_hash,
            lifecycle="APPROVED",
            category=normalize_category(category),
            tags=normalize_tags(tags),
            quality_total=gate.quality_total,
            ic_score=float(score.ic_score) if score else 0.0,
            icir_score=float(score.icir_score) if score else 0.0,
            multiple_testing_warning=gate.multiple_testing_warning,
            metadata={"promotion_gate": gate.model_dump(mode="json")},
        )
        self._persist_entry(entry, inj)
        if inj and inj.auto_activate:
            return self.activate(entry.entry_id)
        return entry

    def promote_to_library(
        self,
        *,
        candidate_id: str | None = None,
        factor_ref: str | None = None,
        evaluation_id: str | None = None,
        operator: str = "",
        category: str = "OTHER",
        tags: list[str] | None = None,
        inject: Mapping[str, Any] | FactorLibraryInject | None = None,
    ) -> FactorLibraryEntry:
        inj = _coerce_inject(inject)
        if self._eval_svc is None:
            raise FactorLibraryError("eval_svc required for promote_to_library")

        cand = None
        mining_meta: dict[str, Any] = {}
        resolved_ref = factor_ref or ""
        resolved_eval = evaluation_id or ""

        if candidate_id:
            if self._mining_svc is None:
                raise FactorLibraryError("mining_svc required when candidate_id set")
            cand = self._mining_svc._find_candidate(candidate_id)  # noqa: SLF001 — 编排层复用
            resolved_ref = cand.factor_ref or resolved_ref
            resolved_eval = cand.evaluation_id or resolved_eval
            idx = self._mining_svc._find_run_index(cand.mining_run_id)  # noqa: SLF001
            if idx:
                mining_meta = dict(idx.metadata or {})

        if not resolved_ref or not resolved_eval:
            raise FactorLibraryError("factor_ref and evaluation_id required")

        run = self._eval_svc.get_run(resolved_eval)
        if run.factor_ref != resolved_ref:
            raise FactorLibraryError("factor_ref does not match evaluation run")

        score = None
        try:
            score = self._eval_svc.get_quality_score(resolved_eval)
        except Exception:
            pass

        gate = evaluate_promotion_gate(
            evaluation_run=run,
            quality_score=score,
            candidate=cand,
            mining_run_metadata=mining_meta,
            inject=inj,
        )
        try:
            assert_promotion_pass(gate)
        except PromotionGateError as exc:
            raise FactorLibraryError(str(exc)) from exc

        meta = {
            "operator": operator,
            "promotion_gate": gate.model_dump(mode="json"),
        }
        if cand:
            meta["candidate_id"] = cand.candidate_id
            meta["mining_run_id"] = cand.mining_run_id

        entry = pin_library_entry(
            factor_ref=resolved_ref,
            factor_hash=run.factor_hash,
            evaluation_id=resolved_eval,
            dataset_ref=run.dataset_ref,
            dataset_hash=run.dataset_hash,
            lifecycle="APPROVED",
            category=normalize_category(category),
            tags=normalize_tags(tags),
            quality_total=gate.quality_total,
            ic_score=float(score.ic_score) if score else 0.0,
            icir_score=float(score.icir_score) if score else 0.0,
            candidate_id=cand.candidate_id if cand else "",
            mining_run_id=cand.mining_run_id if cand else "",
            multiple_testing_warning=gate.multiple_testing_warning,
            metadata=meta,
        )
        self._persist_entry(entry, inj)
        if inj and inj.auto_activate:
            return self.activate(entry.entry_id)
        return entry

    def activate(self, entry_id: str) -> FactorLibraryEntry:
        entry = self._require_entry(entry_id)
        if not can_activate(entry.lifecycle):
            raise LibraryLifecycleError(f"cannot activate from {entry.lifecycle}")
        assert_transition(entry.lifecycle, "ACTIVE")
        updated = entry.model_copy(update={"lifecycle": "ACTIVE"})
        self._persist_entry(updated, None, allow_lifecycle=True)
        return updated

    def deprecate(
        self,
        entry_id: str,
        reason: str,
        *,
        replacement_ref: str = "",
    ) -> FactorLibraryEntry:
        entry = self._require_entry(entry_id)
        if not can_deprecate(entry.lifecycle):
            raise LibraryLifecycleError(f"cannot deprecate from {entry.lifecycle}")
        assert_transition(entry.lifecycle, "DEPRECATED")
        updated = entry.model_copy(
            update={
                "lifecycle": "DEPRECATED",
                "deprecate_reason": reason,
                "replacement_ref": replacement_ref,
            }
        )
        self._persist_entry(updated, None, allow_lifecycle=True)
        return updated

    def retire(self, entry_id: str) -> FactorLibraryEntry:
        entry = self._require_entry(entry_id)
        if not can_retire(entry.lifecycle):
            raise LibraryLifecycleError(f"cannot retire from {entry.lifecycle}")
        assert_transition(entry.lifecycle, "RETIRED")
        updated = entry.model_copy(update={"lifecycle": "RETIRED"})
        self._persist_entry(updated, None, allow_lifecycle=True)
        return updated

    def search(self, query: FactorSearchQuery) -> list[FactorLibraryEntry]:
        return search_entries(self._catalog.list_all(), query)

    def get_entry(self, entry_id: str) -> FactorLibraryEntry:
        return self._require_entry(entry_id)

    def similar_factors(
        self,
        factor_ref: str,
        *,
        top_k: int = 10,
        inject: Mapping[str, Any] | FactorLibraryInject | None = None,
    ) -> list[SimilarFactorHit]:
        inj = _coerce_inject(inject)
        refs = [e.factor_ref for e in self._catalog.list_all()]
        return similar_factors(
            factor_ref,
            catalog_refs=refs,
            inject=inj,
            top_k=top_k,
            corr_matrix=inj.cluster_corr_matrix if inj else None,
        )

    def build_cluster(
        self,
        factor_refs: list[str],
        *,
        policy: FactorClusterPolicy | None = None,
        inject: Mapping[str, Any] | FactorLibraryInject | None = None,
    ) -> FactorCluster:
        inj = _coerce_inject(inject)
        pol = policy or FactorClusterPolicy()
        matrix = inj.cluster_corr_matrix if inj else {}
        cluster = build_factor_cluster(factor_refs, policy=pol, corr_matrix=matrix)
        write_cluster(self._store, cluster)
        self._clusters[cluster.cluster_id] = cluster
        return cluster

    def create_collection(
        self,
        member_refs: list[str],
        *,
        name: str = "",
        version: str = "1.0.0",
    ) -> FactorCollection:
        coll = build_collection(member_refs=member_refs, name=name, version=version)
        write_collection(self._store, coll)
        self._collections[coll.collection_id] = coll
        return coll

    def get_collection(self, collection_id: str) -> FactorCollection:
        coll = self._collections.get(collection_id)
        if coll is None:
            path = self._store.collection_path(collection_id=collection_id)
            coll = load_json_model(path, FactorCollection)
            if coll is None:
                raise FactorLibraryError(f"collection not found: {collection_id}")
            self._collections[collection_id] = coll
        return coll

    def create_portfolio_spec(
        self,
        *,
        member_refs: list[str] | None = None,
        collection_id: str = "",
        weight_method: WeightMethod = "EQUAL",
        name: str = "",
        version: str = "1.0.0",
        inject: Mapping[str, Any] | FactorLibraryInject | None = None,
    ) -> FactorPortfolioSpec:
        inj = _coerce_inject(inject)
        refs = list(member_refs or [])
        if collection_id:
            refs = list(self.get_collection(collection_id).member_refs)
        if not refs:
            raise FactorLibraryError("portfolio requires member_refs or collection_id")
        spec = build_portfolio_spec(
            member_refs=refs,
            weight_method=weight_method,
            collection_id=collection_id,
            name=name,
            version=version,
            metrics=inj.weight_metrics if inj else None,
            corr_matrix=inj.cluster_corr_matrix if inj else None,
        )
        write_portfolio(self._store, spec)
        self._portfolios[spec.portfolio_id] = spec
        return spec

    def get_portfolio_spec(self, portfolio_id: str) -> FactorPortfolioSpec:
        spec = self._portfolios.get(portfolio_id)
        if spec is None:
            path = self._store.portfolio_path(portfolio_id=portfolio_id)
            spec = load_json_model(path, FactorPortfolioSpec)
            if spec is None:
                raise FactorLibraryError(f"portfolio not found: {portfolio_id}")
            self._portfolios[portfolio_id] = spec
        return spec

    def resolve_weights(
        self,
        portfolio_id: str,
        *,
        inject: Mapping[str, Any] | FactorLibraryInject | None = None,
    ) -> dict[str, float]:
        inj = _coerce_inject(inject)
        spec = self.get_portfolio_spec(portfolio_id)
        return resolve_portfolio_weights(
            spec.member_refs,
            method=spec.weight_method,
            metrics=inj.weight_metrics if inj else None,
            corr_matrix=inj.cluster_corr_matrix if inj else None,
        )

    def list_usages(self, factor_ref: str) -> dict[str, list[str]]:
        return list_usages(
            factor_ref,
            entries=self._catalog.list_all(),
            collections=list(self._collections.values()),
            portfolios=list(self._portfolios.values()),
            registry=self._registry,
        )

    def to_feature_set(
        self,
        *,
        collection_id: str = "",
        portfolio_id: str = "",
        code: str,
        version: str,
    ) -> FeatureSetDefinition:
        if collection_id:
            return from_collection(
                self.get_collection(collection_id),
                code=code,
                version=version,
            )
        if portfolio_id:
            return from_portfolio(
                self.get_portfolio_spec(portfolio_id),
                code=code,
                version=version,
            )
        raise FactorLibraryError("collection_id or portfolio_id required")

    def _require_entry(self, entry_id: str) -> FactorLibraryEntry:
        entry = self._catalog.get(entry_id)
        if entry is None:
            path = self._store.entry_path(entry_id=entry_id)
            entry = load_json_model(path, FactorLibraryEntry)
            if entry is None:
                raise FactorLibraryError(f"entry not found: {entry_id}")
            self._catalog.upsert(entry)
        return entry

    def _persist_entry(
        self,
        entry: FactorLibraryEntry,
        inj: FactorLibraryInject | None,
        *,
        allow_lifecycle: bool = False,
    ) -> None:
        existing = self._catalog.get(entry.entry_id)
        if existing and not allow_lifecycle:
            if inj and inj.skip_immutability:
                pass
            else:
                try:
                    assert_entry_immutable(existing, entry)
                except LibraryImmutabilityError as exc:
                    raise FactorLibraryError(str(exc)) from exc
                if existing.lifecycle == entry.lifecycle:
                    return
        write_entry(self._store, entry)
        self._catalog.upsert(entry)
        self._persist_registry(entry)

    def _persist_registry(self, entry: FactorLibraryEntry) -> None:
        if not hasattr(self._registry, "_read"):
            return
        with self._registry._lock:  # type: ignore[attr-defined]
            data = self._registry._read()
            data.setdefault("library_entries", {})[entry.entry_id] = entry.model_dump(
                mode="json"
            )
            self._registry._write(data)


__all__ = [
    "FactorLibraryError",
    "FactorLibraryService",
]
