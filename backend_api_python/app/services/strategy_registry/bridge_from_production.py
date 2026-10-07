"""Phase 8A：APPROVED/DEPLOYED ProductionBundle → StrategyVersionRecord。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from app.services.research_data.contracts import ProductionBundleSummary

from .bindings import normalize_policy_bindings
from .identity import normalize_strategy_code
from .pin import content_hash_for_version_record
from .protocol import StrategyVersionRecord, VersionSource


class BundleNotEligibleError(ValueError):
    """Bundle 状态不允许注册到 Strategy Registry。"""


_ALLOWED_BUNDLE_STATUS = frozenset({"APPROVED", "DEPLOYED"})


def _feature_version_from_bundle(bundle: ProductionBundleSummary) -> str:
    if bundle.feature_hashes:
        return bundle.feature_hashes[0]
    return str(bundle.metadata.get("feature_version") or "")


def _processor_version_from_bundle(bundle: ProductionBundleSummary) -> str:
    meta = bundle.metadata or {}
    return str(meta.get("processor_version") or bundle.processor_hash or "")


def version_record_from_production_bundle(
    bundle: ProductionBundleSummary | Mapping[str, Any],
    *,
    strategy_version_label: str,
    risk_policy_ref: str = "",
    execution_policy_ref: str | None = None,
    source: VersionSource = "BUNDLE",
) -> StrategyVersionRecord:
    """从 ProductionBundle 摘要组装版本记录（不写存储）。"""
    if isinstance(bundle, Mapping):
        bundle = ProductionBundleSummary.model_validate(dict(bundle))
    status = str(bundle.status or "").upper()
    if status not in _ALLOWED_BUNDLE_STATUS:
        raise BundleNotEligibleError(
            f"bundle status {status!r} not in {_ALLOWED_BUNDLE_STATUS}"
        )
    code = normalize_strategy_code(bundle.strategy_code or bundle.metadata.get("strategy_code") or "")
    if not code:
        raise ValueError("bundle.strategy_code required for registry")
    label = str(strategy_version_label or "").strip()
    if not label:
        raise ValueError("strategy_version_label required")

    bindings = normalize_policy_bindings(
        risk_policy_ref=risk_policy_ref,
        execution_policy_ref=execution_policy_ref or bundle.execution_policy or "NEXT_OPEN",
    )
    feature_version = _feature_version_from_bundle(bundle)
    processor_version = _processor_version_from_bundle(bundle)

    content_hash = content_hash_for_version_record(
        strategy_version=label,
        model_version=bundle.model_version,
        dataset_hash=bundle.dataset_hash,
        feature_version=feature_version,
        strategy_hash=bundle.strategy_hash,
        bundle_hash=bundle.bundle_hash,
        snapshot_id=bundle.snapshot_id,
        model_artifact_id=bundle.model_artifact_id,
        processor_version=processor_version,
        processor_hash=bundle.processor_hash,
        risk_policy_ref=bindings.risk_policy_ref,
        execution_policy_ref=bindings.execution_policy_ref,
    )
    version_id = f"{code}@{label}@{content_hash[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    return StrategyVersionRecord(
        version_id=version_id,
        strategy_code=code,
        strategy_version=label,
        dataset_hash=bundle.dataset_hash,
        snapshot_id=bundle.snapshot_id,
        model_version=bundle.model_version,
        model_artifact_id=bundle.model_artifact_id,
        feature_version=feature_version,
        processor_version=processor_version,
        processor_hash=bundle.processor_hash,
        strategy_hash=bundle.strategy_hash,
        bundle_hash=bundle.bundle_hash,
        risk_policy_ref=bindings.risk_policy_ref,
        execution_policy_ref=bindings.execution_policy_ref,
        content_hash=content_hash,
        registered_at=now,
        source=source,
        immutable=True,
        metadata={
            "bundle_status": status,
            "cv_hash": bundle.cv_hash,
            "bridge_ref": str(uuid4()),
        },
    )
