"""Experiment SSOT: list/get/register definitions (no run pipeline in 10E slice)."""

from __future__ import annotations

import uuid
from typing import Any

from app.services.research_data.contracts import ExperimentDefinition
from app.services.research_data.registry import ResearchRegistry, get_default_registry

from .protocol import ExperimentCreateSpec
from ..research_query.dto import ExperimentDetailDto, ExperimentListItemDto


class ExperimentPlatformError(RuntimeError):
    pass


def _to_list_item(exp: ExperimentDefinition) -> ExperimentListItemDto:
    return ExperimentListItemDto(
        experiment_id=exp.experiment_id,
        name=exp.name,
        dataset_ref=exp.dataset_ref,
        status=exp.status,
        model_version_ref=exp.model_version_ref or "",
    )


def _to_detail(exp: ExperimentDefinition) -> ExperimentDetailDto:
    base = _to_list_item(exp)
    return ExperimentDetailDto(
        **base.model_dump(),
        snapshot_id=exp.snapshot_id,
        dataset_hash=exp.dataset_hash,
        feature_refs=list(exp.feature_refs or []),
        processor_ref=exp.processor_ref or "",
        parameters=dict(exp.parameters or {}),
        manifest_uri=exp.manifest_uri or "",
    )


class ExperimentPlatformService:
    def __init__(self, registry: ResearchRegistry | None = None) -> None:
        self._registry = registry or get_default_registry()

    def list_experiments(self) -> list[ExperimentListItemDto]:
        rows = _list_experiments_raw(self._registry)
        items = [ExperimentDefinition.model_validate(r) for r in rows]
        return [_to_list_item(e) for e in sorted(items, key=lambda x: x.experiment_id)]

    def get_experiment(self, experiment_id: str) -> ExperimentDetailDto:
        try:
            exp = self._registry.get_experiment(experiment_id)
        except KeyError as exc:
            raise ExperimentPlatformError(f"experiment not found: {experiment_id}") from exc
        return _to_detail(exp)

    def register_experiment(self, spec: ExperimentCreateSpec) -> ExperimentDetailDto:
        try:
            handle = self._registry.get_dataset(spec.dataset_ref)
        except KeyError as exc:
            raise ExperimentPlatformError(f"dataset not found: {spec.dataset_ref}") from exc

        if spec.model_version_ref:
            _assert_model_ref(self._registry, spec.model_version_ref)

        for fref in spec.feature_refs:
            try:
                self._registry.get_feature(fref)
            except KeyError as exc:
                raise ExperimentPlatformError(f"feature not found: {fref}") from exc

        experiment_id = f"exp_{uuid.uuid4().hex[:16]}"
        definition = ExperimentDefinition(
            experiment_id=experiment_id,
            name=spec.name.strip(),
            dataset_ref=spec.dataset_ref,
            snapshot_id=handle.definition.snapshot_id,
            dataset_hash=handle.dataset_hash,
            model_version_ref=spec.model_version_ref,
            feature_refs=list(spec.feature_refs),
            processor_ref=spec.processor_ref,
            parameters=dict(spec.parameters or {}),
            status="COMPLETED",
        )
        self._registry.upsert_experiment(definition)
        return _to_detail(definition)


def _assert_model_ref(registry: ResearchRegistry, model_version_ref: str) -> None:
    if hasattr(registry, "_read"):
        data = registry._read()  # type: ignore[attr-defined]
        versions = data.get("model_versions") or {}
        if model_version_ref in versions:
            return
        for key in versions:
            raw = versions[key]
            ref = f"{raw.get('model_code')}@{raw.get('version')}"
            if ref == model_version_ref:
                return
    raise ExperimentPlatformError(f"model version not found: {model_version_ref}")


def _list_experiments_raw(registry: ResearchRegistry) -> list[dict[str, Any]]:
    if hasattr(registry, "_read"):
        data = registry._read()  # type: ignore[attr-defined]
        bucket = data.get("experiments") or {}
        return list(bucket.values())
    return []


_service: ExperimentPlatformService | None = None


def get_experiment_platform_service() -> ExperimentPlatformService:
    global _service
    if _service is None:
        _service = ExperimentPlatformService()
    return _service


__all__ = [
    "ExperimentPlatformError",
    "ExperimentPlatformService",
    "get_experiment_platform_service",
]
