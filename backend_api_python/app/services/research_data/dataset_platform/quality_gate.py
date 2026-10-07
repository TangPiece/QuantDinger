"""Dataset 发布前质量门：universe / snapshot / PIT / price_policy / checksum。"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.research_data.contracts import DatasetDefinition, PricePolicy

from .protocol import DatasetBuildInject, QualityGateResult


class DatasetQualityGateError(ValueError):
    """Gate 拒绝发布。"""


def _price_policy_complete(policy: PricePolicy) -> bool:
    adj = str(policy.adjustment or "").strip()
    ret = str(policy.return_type or "").strip()
    return adj in ("none", "pre", "post") and ret in ("price", "total")


def evaluate_dataset_build(
    definition: DatasetDefinition,
    *,
    snapshot_items: list[dict[str, Any]],
    inject: Mapping[str, Any] | DatasetBuildInject | None = None,
) -> QualityGateResult:
    """校验 Definition + snapshot 条目；inject 可注入 gate_override。"""
    inj = _normalize_inject(inject)
    override = inj.gate_override if inj else None
    if isinstance(override, dict):
        verdict = str(override.get("verdict") or "PASS").upper()
        reasons = [str(x) for x in (override.get("reasons") or [])]
        if verdict == "REJECT":
            return QualityGateResult(verdict="REJECT", reasons=reasons or ["inject_reject"])

    reasons: list[str] = []
    items = list(snapshot_items or [])
    if inj and inj.force_empty_snapshot:
        items = []

    if not str(definition.universe_code or "").strip():
        reasons.append("empty_universe_code")
    if not str(definition.universe_version or "").strip():
        reasons.append("empty_universe_version")
    if not definition.features:
        reasons.append("empty_features")
    if not items:
        reasons.append("empty_snapshot")
    pit_ok = definition.pit
    if inj and inj.force_pit_false:
        pit_ok = False
    if not pit_ok:
        reasons.append("pit_disabled")
    if not _price_policy_complete(definition.price_policy):
        reasons.append("incomplete_price_policy")

    for idx, it in enumerate(items):
        cs = str(it.get("checksum") or "").strip()
        if inj and inj.strip_checksums:
            cs = ""
        if not cs:
            reasons.append(f"missing_item_checksum:{idx}")
            break

    if reasons:
        return QualityGateResult(verdict="REJECT", reasons=reasons)
    return QualityGateResult(verdict="PASS")


def assert_quality_gate(result: QualityGateResult) -> None:
    if result.verdict != "PASS":
        raise DatasetQualityGateError("; ".join(result.reasons) or "quality_gate_rejected")


def _normalize_inject(
    inject: Mapping[str, Any] | DatasetBuildInject | None,
) -> DatasetBuildInject | None:
    if inject is None:
        return None
    if isinstance(inject, DatasetBuildInject):
        return inject
    section = inject.get("dataset_platform") if isinstance(inject, dict) else None
    if isinstance(section, dict):
        return DatasetBuildInject.model_validate(section)
    if isinstance(inject, dict) and ("gate_override" in inject or "force_empty_snapshot" in inject):
        return DatasetBuildInject.model_validate(inject)
    return None


__all__ = [
    "DatasetQualityGateError",
    "assert_quality_gate",
    "evaluate_dataset_build",
]
