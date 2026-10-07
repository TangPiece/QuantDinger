"""注册 / 构建前质量门。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from app.services.research_data.contracts import DatasetHandle, FeatureDefinition
from app.services.research_data.factor_lab.dependencies import validate_dependencies

from .feature_set import FeatureSetDefinition
from .pipeline import FactorPipelineSpec, PIPELINE_DEF_KEY
from .protocol import FeatureFactorBuildInject, QualityGateResult
from .taxonomy import ASSET_KIND_KEY, AssetKind, read_asset_kind


class FeatureFactorQualityGateError(ValueError):
    """Gate 拒绝。"""


def evaluate_register_feature(feature: FeatureDefinition) -> QualityGateResult:
    reasons: list[str] = []
    sidecar = feature.definition or {}
    ak = sidecar.get(ASSET_KIND_KEY)
    if ak is not None and str(ak).upper() != AssetKind.FEATURE.value:
        reasons.append("wrong_asset_kind_for_register_feature")
    if sidecar.get(PIPELINE_DEF_KEY):
        reasons.append("factor_pipeline_on_feature")
    if not str(feature.expression or "").strip():
        reasons.append("empty_expression")
    return _finish(reasons)


def evaluate_register_factor(
    feature: FeatureDefinition,
    pipeline: FactorPipelineSpec | None,
) -> QualityGateResult:
    reasons: list[str] = []
    sidecar = feature.definition or {}
    ak = sidecar.get(ASSET_KIND_KEY)
    if ak is not None and str(ak).upper() != AssetKind.FACTOR.value:
        reasons.append("wrong_asset_kind_for_register_factor")
    if pipeline is not None:
        reasons.extend(pipeline.validate_fields())
    return _finish(reasons)


def evaluate_register_alpha(feature: FeatureDefinition) -> QualityGateResult:
    reasons: list[str] = []
    if read_asset_kind(feature) != AssetKind.ALPHA:
        reasons.append("wrong_asset_kind_for_register_alpha")
    sidecar = feature.definition or {}
    if not str(feature.expression or "").strip() and not sidecar.get("weights"):
        reasons.append("alpha_missing_expression_or_weights")
    return _finish(reasons)


def evaluate_feature_set(definition: FeatureSetDefinition) -> QualityGateResult:
    reasons: list[str] = []
    if not definition.member_refs:
        reasons.append("empty_feature_set_members")
    return _finish(reasons)


def evaluate_factor_build(
    feature: FeatureDefinition,
    handle: DatasetHandle,
    *,
    manifest_path: Path | None,
    registry: Any,
    inject: Mapping[str, Any] | FeatureFactorBuildInject | None = None,
) -> QualityGateResult:
    inj = _normalize_inject(inject)
    override = inj.gate_override if inj else None
    if isinstance(override, dict):
        verdict = str(override.get("verdict") or "PASS").upper()
        reasons = [str(x) for x in (override.get("reasons") or [])]
        if verdict == "REJECT":
            return QualityGateResult(verdict="REJECT", reasons=reasons or ["inject_reject"])

    reasons: list[str] = []
    if not handle.manifest_uri and not (inj and inj.skip_dataset_manifest_check):
        reasons.append("dataset_manifest_uri_missing")
    if manifest_path is not None and not inj.skip_dataset_manifest_check:
        if not manifest_path.is_file():
            reasons.append("dataset_manifest_file_missing")
    if not handle.definition.pit:
        reasons.append("dataset_pit_disabled")
    try:
        validate_dependencies(feature, registry, check_cycles=True)
    except Exception as exc:
        reasons.append(f"dependency_invalid:{exc}")

    pipe_raw = (feature.definition or {}).get(PIPELINE_DEF_KEY)
    if pipe_raw is not None:
        try:
            spec = FactorPipelineSpec.model_validate(pipe_raw)
            reasons.extend(spec.validate_fields())
        except Exception:
            reasons.append("invalid_factor_pipeline")

    return _finish(reasons)


def assert_quality_gate(result: QualityGateResult) -> None:
    if result.verdict != "PASS":
        raise FeatureFactorQualityGateError("; ".join(result.reasons) or "quality_gate_rejected")


def _finish(reasons: list[str]) -> QualityGateResult:
    if reasons:
        return QualityGateResult(verdict="REJECT", reasons=reasons)
    return QualityGateResult(verdict="PASS")


def _normalize_inject(
    inject: Mapping[str, Any] | FeatureFactorBuildInject | None,
) -> FeatureFactorBuildInject | None:
    if inject is None:
        return None
    if isinstance(inject, FeatureFactorBuildInject):
        return inject
    section = inject.get("feature_factor_platform") if isinstance(inject, dict) else None
    if isinstance(section, dict):
        return FeatureFactorBuildInject.model_validate(section)
    if isinstance(inject, dict) and any(
        k in inject for k in FeatureFactorBuildInject.model_fields
    ):
        return FeatureFactorBuildInject.model_validate(inject)
    return None


__all__ = [
    "FeatureFactorQualityGateError",
    "assert_quality_gate",
    "evaluate_factor_build",
    "evaluate_feature_set",
    "evaluate_register_alpha",
    "evaluate_register_factor",
    "evaluate_register_feature",
]
