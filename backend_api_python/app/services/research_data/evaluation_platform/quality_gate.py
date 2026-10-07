"""评价前 QualityGate：钉住 9B build + 9A dataset lineage。"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.research_data.contracts import DatasetHandle, FeatureDefinition
from app.services.research_data.feature_factor_platform.protocol import FactorBuildIndex

from .protocol import EvaluationPlatformInject, QualityGateResult


class EvaluationQualityGateError(ValueError):
    """Gate 拒绝（→ BLOCKED run）。"""


def evaluate_evaluation_run(
    *,
    feature: FeatureDefinition,
    handle: DatasetHandle,
    build_index: FactorBuildIndex,
    registry: Any,
    inject: Mapping[str, Any] | EvaluationPlatformInject | None = None,
) -> QualityGateResult:
    inj = _normalize_inject(inject)
    override = inj.gate_override if inj else None
    if isinstance(override, dict):
        verdict = str(override.get("verdict") or "PASS").upper()
        reasons = [str(x) for x in (override.get("reasons") or [])]
        if verdict == "BLOCKED":
            return QualityGateResult(verdict="BLOCKED", reasons=reasons or ["inject_blocked"])
        if verdict == "PASS":
            return QualityGateResult(verdict="PASS", reasons=reasons)

    reasons: list[str] = []
    if not handle.definition.pit:
        reasons.append("dataset_pit_disabled")
    if not (handle.manifest_uri or "").strip() and not (inj and inj.skip_build_resolve):
        reasons.append("dataset_manifest_uri_missing")
    if build_index.dataset_hash != handle.dataset_hash:
        reasons.append("build_index_dataset_hash_mismatch")
    if build_index.factor_hash != str(feature.factor_hash or ""):
        reasons.append("build_index_factor_hash_mismatch")
    if not (build_index.factor_dataset_id or "").strip():
        reasons.append("factor_dataset_id_missing")
    sidecar = feature.definition or {}
    if str(sidecar.get("asset_kind") or "").upper() not in ("", "FACTOR"):
        reasons.append("not_a_factor_asset")

    try:
        registry.get_factor_dataset(build_index.factor_dataset_id)
    except Exception as exc:
        reasons.append(f"factor_dataset_not_registered:{exc}")

    return _finish(reasons)


def assert_quality_gate(result: QualityGateResult) -> None:
    if result.verdict != "PASS":
        raise EvaluationQualityGateError("; ".join(result.reasons) or "quality_gate_blocked")


def _finish(reasons: list[str]) -> QualityGateResult:
    if reasons:
        return QualityGateResult(verdict="BLOCKED", reasons=reasons)
    return QualityGateResult(verdict="PASS")


def _normalize_inject(
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
    "EvaluationQualityGateError",
    "assert_quality_gate",
    "evaluate_evaluation_run",
]
