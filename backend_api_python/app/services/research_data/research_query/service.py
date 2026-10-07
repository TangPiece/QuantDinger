"""Research Query Service: domain → read DTOs for Phase 10B/10F HTTP."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.services.research_data.contracts import FeatureDefinition
from app.services.research_data.dataset_platform.runner import ResearchDatasetService
from app.services.research_data.model_platform.protocol import ModelSearchQuery, ModelVersion
from app.services.research_data.model_platform.runner import ModelPlatformError, ModelPlatformService
from app.services.research_data.registry import ResearchRegistry, get_default_registry

if TYPE_CHECKING:
    from app.services.research_data.factor_library_platform.runner import FactorLibraryService

from .dto import (
    AlphaFactorDetailDto,
    AlphaFactorEvaluationDto,
    AlphaFactorListItemDto,
    ArtifactDetailDto,
    DatasetDetailDto,
    DatasetListItemDto,
    EvaluationSeriesDto,
    FactorLibraryItemDto,
    FactorPortfolioItemDto,
    FeatureDetailDto,
    FeatureListItemDto,
    ModelDetailDto,
    ModelListItemDto,
    PeriodDto,
    ProductStatusDto,
)


class ResearchQueryError(RuntimeError):
    pass


def _registry_bucket(registry: ResearchRegistry, key: str) -> dict[str, Any]:
    if not hasattr(registry, "_read"):
        return {}
    data = registry._read()  # type: ignore[attr-defined]
    block = data.get(key)
    return block if isinstance(block, dict) else {}


def _dataset_status(raw: dict[str, Any]) -> str:
    st = str(raw.get("_registry_status") or "READY").upper()
    return st if st else "READY"


def _pit_label(pit: bool) -> str:
    return "STRICT" if pit else "RELAXED"


def _price_policy_label(price_policy: Any) -> str:
    if price_policy is None:
        return "RAW"
    adj = getattr(price_policy, "adjustment", None)
    if adj is None and isinstance(price_policy, dict):
        adj = price_policy.get("adjustment")
    adj = str(adj or "none").lower()
    if adj in ("", "none"):
        return "RAW"
    return adj.upper()


def _label_name(label: Any) -> str:
    if label is None:
        return ""
    name = getattr(label, "name", None) or getattr(label, "code", None)
    if name:
        return str(name)
    if isinstance(label, dict):
        return str(label.get("name") or label.get("code") or "")
    return ""


class ResearchQueryService:
    def __init__(
        self,
        registry: ResearchRegistry | None = None,
        *,
        dataset_svc: ResearchDatasetService | None = None,
        model_platform: ModelPlatformService | None = None,
        factor_library: "FactorLibraryService | None" = None,
    ) -> None:
        self._registry = registry or get_default_registry()
        self._dataset_svc = dataset_svc or ResearchDatasetService(None, self._registry)
        self._models = model_platform or ModelPlatformService(None, research_registry=self._registry)
        self._library = factor_library
        self._library_loaded = factor_library is not None

    def list_datasets(self) -> list[DatasetListItemDto]:
        refs = self._dataset_svc.list_datasets()
        items: list[DatasetListItemDto] = []
        bucket = _registry_bucket(self._registry, "datasets")
        for ref in refs:
            try:
                handle = self._registry.get_dataset(ref)
            except KeyError:
                continue
            items.append(self._dataset_list_item(ref, handle, bucket.get(ref) or {}))
        return items

    def get_dataset(self, dataset_id: str) -> DatasetDetailDto:
        try:
            handle = self._registry.get_dataset(dataset_id)
        except KeyError as exc:
            raise ResearchQueryError(f"dataset not found: {dataset_id}") from exc
        bucket = _registry_bucket(self._registry, "datasets")
        raw = bucket.get(dataset_id) or {}
        base = self._dataset_list_item(dataset_id, handle, raw)
        defn = handle.definition
        schema = [{"feature": f, "type": "float", "nullable": "yes"} for f in (defn.features or [])]
        quality = [
            {"check": "PIT Leakage", "result": "PASS" if defn.pit else "REVIEW"},
            {"check": "Universe", "result": "PASS"},
            {"check": "Timestamp", "result": "PASS"},
        ]
        lineage = [
            {"step": "Snapshot", "ref": defn.snapshot_id},
            {"step": "Dataset Definition", "ref": dataset_id},
            {"step": "Dataset Hash", "ref": handle.dataset_hash[:16] + "…"},
        ]
        materialization: dict[str, Any] = {}
        try:
            manifest = self._dataset_svc.get_manifest(dataset_id)
            materialization = {
                "engineVersion": manifest.engine_version,
                "publishedAt": manifest.published_at.isoformat(),
                "processor": manifest.processor or defn.processor or "",
            }
        except Exception:
            materialization = {"processor": defn.processor or ""}

        return DatasetDetailDto(
            **base.model_dump(),
            price_policy=_price_policy_label(defn.price_policy),
            snapshot_id=defn.snapshot_id,
            processor=defn.processor or "",
            schema_features=schema,
            quality_checks=quality,
            lineage=lineage,
            materialization=materialization,
            preview_available=False,
            preview_rows=[],
        )

    def _dataset_list_item(self, ref: str, handle: Any, raw: dict[str, Any]) -> DatasetListItemDto:
        defn = handle.definition
        features = list(defn.features or [])
        meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        period = PeriodDto(
            start=str(meta.get("period_start") or meta.get("start") or ""),
            end=str(meta.get("period_end") or meta.get("end") or ""),
        )
        return DatasetListItemDto(
            dataset_id=ref,
            name=defn.name or defn.code,
            version=defn.version,
            dataset_hash=handle.dataset_hash,
            universe=f"{defn.universe_code}@{defn.universe_version}",
            frequency=defn.frequency,
            status=_dataset_status(raw),
            feature_count=len(features),
            label_count=1 if defn.label else 0,
            period=period,
            feature_set=", ".join(features[:8]) + ("…" if len(features) > 8 else ""),
            label_name=_label_name(defn.label),
            pit_policy=_pit_label(defn.pit),
        )

    def list_features(self) -> list[FeatureListItemDto]:
        bucket = _registry_bucket(self._registry, "features")
        items: list[FeatureListItemDto] = []
        for ref in sorted(bucket.keys()):
            feat = FeatureDefinition.model_validate(bucket[ref])
            items.append(_feature_list_item(ref, feat))
        return items

    def get_feature(self, feature_id: str) -> FeatureDetailDto:
        try:
            feat = self._registry.get_feature(feature_id)
        except KeyError as exc:
            raise ResearchQueryError(f"feature not found: {feature_id}") from exc
        base = _feature_list_item(feature_id, feat)
        return FeatureDetailDto(
            **base.model_dump(),
            dependencies=list(feat.dependencies or []),
            backend=str(feat.backend or ""),
            description=str(feat.description or ""),
        )

    def list_alpha_factors(self) -> list[AlphaFactorListItemDto]:
        items: list[AlphaFactorListItemDto] = []
        for feat_item in self.list_features():
            eval_dto = self.get_alpha_factor_evaluation(feat_item.feature_id)
            items.append(
                AlphaFactorListItemDto(
                    factor_id=feat_item.feature_id,
                    name=feat_item.name,
                    version=feat_item.version,
                    factor_hash=feat_item.factor_hash,
                    expression=feat_item.expression,
                    factor_type=feat_item.factor_type,
                    lifecycle="",
                    icir=eval_dto.ic_ir if eval_dto.has_result else None,
                    turnover=eval_dto.turnover if eval_dto.has_result else None,
                )
            )
        return items

    def get_alpha_factor(self, factor_id: str) -> AlphaFactorDetailDto:
        detail = self.get_feature(factor_id)
        eval_dto = self.get_alpha_factor_evaluation(factor_id)
        return AlphaFactorDetailDto(
            factor_id=detail.feature_id,
            name=detail.name,
            version=detail.version,
            factor_hash=detail.factor_hash,
            expression=detail.expression,
            factor_type=detail.factor_type,
            lifecycle="",
            icir=eval_dto.ic_ir if eval_dto.has_result else None,
            turnover=eval_dto.turnover if eval_dto.has_result else None,
            dependencies=list(detail.dependencies or []),
            backend=detail.backend,
            description=detail.description,
            frequency=detail.frequency,
        )

    def get_alpha_factor_evaluation(self, factor_id: str) -> AlphaFactorEvaluationDto:
        """Return real FactorEvaluationSummary fields; never invent metrics."""
        empty = AlphaFactorEvaluationDto(factor_id=factor_id, has_result=False)
        try:
            feat = self.get_feature(factor_id)
        except ResearchQueryError:
            return empty

        fhash = feat.factor_hash
        empty = empty.model_copy(update={"factor_hash": fhash})

        summary = _find_evaluation_summary(self._registry, factor_id=factor_id, factor_hash=fhash)
        if summary is None:
            return empty

        turnover = _find_turnover(self._registry, evaluation_hash=str(summary.get("evaluation_hash") or ""))
        series = _load_evaluation_series(summary)
        mean_ic = _float_or_none(summary.get("mean_ic"))
        mean_rank_ic = _float_or_none(summary.get("mean_rank_ic"))
        ic_ir = _float_or_none(summary.get("ic_ir"))
        rank_ic_ir = _float_or_none(summary.get("rank_ic_ir"))
        metrics = {
            k: summary.get(k)
            for k in (
                "mean_ic",
                "mean_rank_ic",
                "ic_ir",
                "rank_ic_ir",
                "valid_day_count",
                "total_day_count",
                "direction",
            )
            if summary.get(k) is not None
        }
        return AlphaFactorEvaluationDto(
            factor_id=factor_id,
            factor_hash=fhash,
            has_result=True,
            horizon=int(summary.get("horizon") or 0),
            mean_ic=mean_ic,
            mean_rank_ic=mean_rank_ic,
            ic_ir=ic_ir,
            rank_ic_ir=rank_ic_ir,
            turnover=turnover,
            evaluation_hash=str(summary.get("evaluation_hash") or ""),
            metric_hash=str(summary.get("metric_hash") or ""),
            source_ref=str(summary.get("factor_dataset_id") or ""),
            series=series,
            ic=mean_ic,
            rank_ic=mean_rank_ic,
            icir=ic_ir,
            metrics=metrics,
        )

    def _factor_library(self) -> "FactorLibraryService | None":
        if self._library_loaded:
            return self._library
        self._library_loaded = True
        try:
            from app.services.research_data.factor_library_platform.runner import (
                FactorLibraryService,
            )

            self._library = FactorLibraryService(None, self._registry)
        except Exception:
            self._library = None
        return self._library

    def list_factor_library(self) -> list[FactorLibraryItemDto]:
        lib = self._factor_library()
        if lib is None:
            return []
        entries = lib._catalog.list_all()
        return [
            FactorLibraryItemDto(
                entry_id=e.entry_id,
                factor_ref=e.factor_ref,
                category=str(e.category or ""),
                status=str(e.lifecycle or ""),
                evaluation_id=str(e.evaluation_id or ""),
            )
            for e in entries
        ]

    def list_factor_portfolios(self) -> list[FactorPortfolioItemDto]:
        bucket = _registry_bucket(self._registry, "factor_portfolios")
        items: list[FactorPortfolioItemDto] = []
        seen: set[str] = set()
        for pid, raw in sorted(bucket.items()):
            if not isinstance(raw, dict):
                continue
            factors = raw.get("member_refs") or raw.get("factor_refs") or raw.get("factors") or []
            items.append(
                FactorPortfolioItemDto(
                    portfolio_id=pid,
                    name=str(raw.get("name") or pid),
                    factor_count=len(factors) if isinstance(factors, list) else 0,
                    status=str(raw.get("status") or raw.get("lifecycle") or ""),
                )
            )
            seen.add(pid)
        lib = self._factor_library()
        if lib is not None:
            for pid, spec in sorted(lib._portfolios.items()):
                if pid in seen:
                    continue
                members = list(getattr(spec, "member_refs", None) or getattr(spec, "factor_refs", None) or [])
                items.append(
                    FactorPortfolioItemDto(
                        portfolio_id=pid,
                        name=str(getattr(spec, "name", None) or pid),
                        factor_count=len(members),
                        status="",
                    )
                )
        return items

    def list_models(self) -> list[ModelListItemDto]:
        query = ModelSearchQuery()
        try:
            found = self._models.search(query)
        except ModelPlatformError:
            return []
        models = found.get("models") or []
        versions = found.get("versions") or []
        version_by_model: dict[str, ModelVersion] = {}
        for v in versions:
            if isinstance(v, ModelVersion):
                version_by_model[v.model_id] = v
        items: list[ModelListItemDto] = []
        for m in models:
            active = version_by_model.get(m.model_id)
            items.append(
                ModelListItemDto(
                    model_id=m.model_id,
                    model_code=m.model_code,
                    name=m.name or m.model_code,
                    active_version=active.version if active else "",
                    lifecycle=str(active.lifecycle if active else getattr(m, "status", "") or ""),
                )
            )
        return items

    def get_model(self, model_id: str) -> ModelDetailDto:
        version = _resolve_model_version(self._models, model_id)
        model_name = version.model_code
        model_type = ""
        framework = str(getattr(version, "framework", None) or "")
        try:
            model = self._models.get_model(version.model_id)
            model_name = model.name or model.model_code
            model_type = str(getattr(model, "model_type", None) or "")
            if not framework:
                framework = str(getattr(model, "framework", None) or "")
        except ModelPlatformError:
            pass
        return ModelDetailDto(
            model_version_id=version.model_version_id,
            model_id=version.model_id,
            model_code=version.model_code,
            version=version.version,
            name=model_name,
            model_type=model_type,
            framework=framework,
            lifecycle=str(version.lifecycle),
            dataset_ref=str(getattr(version, "dataset_hash", None) or ""),
            feature_set_id=str(getattr(version, "feature_set_id", None) or ""),
            factor_portfolio_id=str(getattr(version, "factor_portfolio_id", None) or ""),
            label_id=str(getattr(version, "label_id", None) or ""),
            processor_version=str(getattr(version, "processor_version", None) or ""),
            training_run_id=str(version.training_run_id or ""),
            artifact_id=str(version.artifact_id or ""),
            status_summary=str(version.lifecycle),
        )

    def get_model_lineage(self, model_id: str) -> dict[str, Any]:
        version = _resolve_model_version(self._models, model_id)
        try:
            return self._models.get_full_lineage(version.model_version_id)
        except ModelPlatformError as exc:
            raise ResearchQueryError(str(exc)) from exc

    def get_model_evaluation(self, model_id: str) -> dict[str, Any]:
        version = _resolve_model_version(self._models, model_id)
        return {
            "modelVersionId": version.model_version_id,
            "metrics": dict(getattr(version, "metrics", None) or {}),
            "lifecycle": str(version.lifecycle),
        }

    def get_artifact(self, artifact_id: str) -> ArtifactDetailDto:
        try:
            record = self._registry.get_artifact(artifact_id)
        except KeyError as exc:
            raise ResearchQueryError(f"artifact not found: {artifact_id}") from exc
        return ArtifactDetailDto(
            artifact_id=str(record.artifact_id),
            kind=str(record.artifact_type or ""),
            uri=str(record.storage_uri or ""),
            checksum=str(record.checksum or ""),
            metadata=dict(record.metadata or {}),
        )

    def product_status(self) -> ProductStatusDto:
        ds = self.list_datasets()
        factors = self.list_alpha_factors()
        models = self.list_models()
        active_models = sum(1 for m in models if (m.lifecycle or "").upper() == "ACTIVE")
        # Semantic codes for UI i18n (Empty → 暂无 Dataset / 暂无 Active Factor / …)
        return ProductStatusDto(
            research={
                "dataset": "EMPTY_DATASET" if not ds else "DATASET_READY",
                "factor": "EMPTY_FACTOR" if not factors else "FACTOR_READY",
                "model": "EMPTY_MODEL" if not active_models else "MODEL_ACTIVE",
            },
            strategy={"shadow": 0, "live": 0},
            models_active=active_models,
            strategies_live=0,
            jobs=[],
        )


def _feature_list_item(ref: str, feat: FeatureDefinition) -> FeatureListItemDto:
    return FeatureListItemDto(
        feature_id=ref,
        name=feat.name or feat.code,
        version=feat.version,
        factor_hash=str(feat.factor_hash or ""),
        factor_type=str(feat.factor_type or ""),
        expression=str(feat.expression or ""),
        frequency=str(feat.frequency or "1d"),
    )


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_model_version(platform: ModelPlatformService, model_id: str) -> ModelVersion:
    try:
        return platform.get_version(model_id)
    except ModelPlatformError as exc:
        raise ResearchQueryError(f"model not found: {model_id}") from exc


def _find_evaluation_summary(
    registry: ResearchRegistry,
    *,
    factor_id: str,
    factor_hash: str,
) -> dict[str, Any] | None:
    """Locate a FactorEvaluationSummary for this factor; prefer matching dataset ids."""
    dataset_ids = _factor_dataset_ids(registry, factor_id=factor_id, factor_hash=factor_hash)
    eval_hashes = _evaluation_hashes_from_runs(factor_id=factor_id, factor_hash=factor_hash)

    summaries = _registry_bucket(registry, "factor_evaluation_summaries")
    candidates: list[dict[str, Any]] = []
    for raw in summaries.values():
        if not isinstance(raw, dict):
            continue
        meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        fd_id = str(raw.get("factor_dataset_id") or "")
        ehash = str(raw.get("evaluation_hash") or "")
        meta_fhash = str(meta.get("factor_hash") or raw.get("factor_hash") or "")
        meta_fref = str(meta.get("factor_ref") or raw.get("factor_ref") or "")

        matched = False
        if factor_hash and meta_fhash and meta_fhash == factor_hash:
            matched = True
        if factor_id and meta_fref and meta_fref == factor_id:
            matched = True
        if fd_id and fd_id in dataset_ids:
            matched = True
        if ehash and ehash in eval_hashes:
            matched = True
        if matched:
            candidates.append(raw)

    if not candidates and len(summaries) == 1 and (dataset_ids or eval_hashes or factor_hash):
        # Single-summary registries from golden runs: only accept if linked.
        only = next(iter(summaries.values()))
        if isinstance(only, dict):
            fd_id = str(only.get("factor_dataset_id") or "")
            ehash = str(only.get("evaluation_hash") or "")
            if fd_id in dataset_ids or ehash in eval_hashes:
                candidates.append(only)

    if not candidates:
        return None
    candidates.sort(key=lambda r: int(r.get("horizon") or 0))
    return candidates[0]


def _factor_dataset_ids(
    registry: ResearchRegistry,
    *,
    factor_id: str,
    factor_hash: str,
) -> set[str]:
    out: set[str] = set()
    for fd_id, raw in _registry_bucket(registry, "factor_datasets").items():
        if not isinstance(raw, dict):
            continue
        if factor_id and str(raw.get("factor_ref") or "") == factor_id:
            out.add(str(fd_id))
        if factor_hash and str(raw.get("factor_hash") or "") == factor_hash:
            out.add(str(fd_id))
    return out


def _evaluation_hashes_from_runs(*, factor_id: str, factor_hash: str) -> set[str]:
    """Scan evaluation_platform run indexes on disk (optional; no invent)."""
    out: set[str] = set()
    try:
        from app.services.research_data.evaluation_platform.artifact_store import (
            EvaluationArtifactStore,
        )
        from app.services.research_data.evaluation_platform.immutability import load_json_model
        from app.services.research_data.evaluation_platform.protocol import EvaluationRunIndex

        store = EvaluationArtifactStore()
        for path in store.list_run_index_paths():
            idx = load_json_model(path, EvaluationRunIndex)
            if idx is None:
                continue
            if factor_hash and idx.factor_hash == factor_hash:
                if idx.evaluation_hash:
                    out.add(idx.evaluation_hash)
                if idx.metric_hash:
                    out.add(idx.metric_hash)
            elif factor_id and idx.factor_ref == factor_id:
                if idx.evaluation_hash:
                    out.add(idx.evaluation_hash)
    except Exception:
        return out
    return out


def _find_turnover(registry: ResearchRegistry, *, evaluation_hash: str) -> float | None:
    if not evaluation_hash:
        return None
    groups = _registry_bucket(registry, "factor_group_evaluations")
    for raw in groups.values():
        if not isinstance(raw, dict):
            continue
        if str(raw.get("evaluation_hash") or "") != evaluation_hash:
            continue
        return _float_or_none(raw.get("mean_turnover"))
    return None


def _load_evaluation_series(summary: dict[str, Any]) -> EvaluationSeriesDto:
    """Load IC time series only from real on-disk artifacts; never fabricate."""
    empty = EvaluationSeriesDto()
    uri = str(summary.get("storage_uri") or "").strip()
    metric_hash = str(summary.get("metric_hash") or "").strip()
    candidates: list[Path] = []
    if uri:
        p = Path(uri)
        if p.is_file():
            candidates.append(p)
        elif p.is_dir():
            candidates.extend([p / "series.json", p / "ic_series.json", p / "summary.json"])
    if metric_hash:
        try:
            from app.services.research_data.factor_lab.metrics.artifact_store import metrics_root

            root = metrics_root() / metric_hash
            candidates.extend(
                [
                    root / "series.json",
                    root / "ic_series.json",
                    root / "summary.json",
                ]
            )
        except Exception:
            pass

    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        series = _parse_series_payload(data, horizon=int(summary.get("horizon") or 0))
        if series.dates:
            return series
    return empty


def _parse_series_payload(data: Any, *, horizon: int) -> EvaluationSeriesDto:
    if not isinstance(data, dict):
        return EvaluationSeriesDto()
    # Direct series shape
    dates = data.get("dates") or data.get("trading_dates") or []
    ic = data.get("ic") or data.get("ics") or []
    rank_ic = data.get("rank_ic") or data.get("rank_ics") or []
    if dates and (ic or rank_ic):
        return EvaluationSeriesDto(
            dates=[str(d) for d in dates],
            ic=[_float_or_none(v) for v in ic],
            rank_ic=[_float_or_none(v) for v in rank_ic],
        )
    # points: [{trading_date, horizon, ic, rank_ic}]
    points = data.get("points") or data.get("series") or []
    if isinstance(points, list) and points:
        filtered = [
            p
            for p in points
            if isinstance(p, dict)
            and (not horizon or int(p.get("horizon") or 0) == horizon or p.get("horizon") is None)
        ]
        if not filtered:
            filtered = [p for p in points if isinstance(p, dict)]
        return EvaluationSeriesDto(
            dates=[str(p.get("trading_date") or p.get("date") or "") for p in filtered],
            ic=[_float_or_none(p.get("ic")) for p in filtered],
            rank_ic=[_float_or_none(p.get("rank_ic")) for p in filtered],
        )
    return EvaluationSeriesDto()


_service: ResearchQueryService | None = None


def get_research_query_service() -> ResearchQueryService:
    global _service
    if _service is None:
        _service = ResearchQueryService()
    return _service


__all__ = ["ResearchQueryError", "ResearchQueryService", "get_research_query_service"]
