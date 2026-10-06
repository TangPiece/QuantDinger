"""Deploy / Pause / Rollback（切换指针，不改旧 Bundle）。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.research_data.contracts import (
    ProductionBundleSummary,
    ProductionDeploymentSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .state_machine import StateTransitionError, assert_transition
from .writers import ProductionBundleWriter


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def deploy_bundle(
    registry: ResearchRegistry,
    writer: ProductionBundleWriter,
    summary: ProductionBundleSummary,
) -> tuple[ProductionBundleSummary, ProductionDeploymentSummary]:
    """APPROVED 或 PAUSED → DEPLOYED；同 strategy_code 仅一个 DEPLOYED。"""
    if summary.status == "PAUSED":
        assert_transition("PAUSED", "DEPLOYED")
    elif summary.status == "APPROVED":
        assert_transition("APPROVED", "DEPLOYED")
    elif summary.status == "DEPLOYED":
        # idempotent
        pass
    else:
        raise StateTransitionError(
            f"cannot deploy from status={summary.status}"
        )

    code = summary.strategy_code or summary.strategy_hash[:16]
    previous = ""
    try:
        active = registry.get_active_deployment(code)
        if active.bundle_hash != summary.bundle_hash and active.status == "DEPLOYED":
            previous = active.bundle_hash
            # 旧部署标 RETIRED（指针切换）
            old = active.model_copy(
                update={"status": "RETIRED", "metadata": {**(active.metadata or {}), "replaced_by": summary.bundle_hash}}
            )
            writer.write_deployment(old)
            # 旧 bundle 若仍 DEPLOYED → RETIRED
            try:
                old_b = registry.get_production_bundle(previous)
                if old_b.status == "DEPLOYED":
                    writer.update_status(previous, "RETIRED")
            except KeyError:
                pass
    except KeyError:
        pass

    updated = writer.update_status(summary.bundle_hash, "DEPLOYED")
    dep = ProductionDeploymentSummary(
        deployment_id=uuid.uuid4().hex,
        bundle_hash=summary.bundle_hash,
        strategy_code=code,
        status="DEPLOYED",
        previous_bundle_hash=previous,
        deployed_at=_utc_now(),
        created_at=_utc_now(),
    )
    writer.write_deployment(dep)
    return updated, dep


def pause_bundle(
    writer: ProductionBundleWriter, summary: ProductionBundleSummary
) -> ProductionBundleSummary:
    assert_transition(summary.status, "PAUSED")
    return writer.update_status(summary.bundle_hash, "PAUSED")


def rollback_deployment(
    registry: ResearchRegistry,
    writer: ProductionBundleWriter,
    *,
    strategy_code: str,
    to_bundle_hash: str,
) -> tuple[ProductionBundleSummary, ProductionDeploymentSummary]:
    """回滚到历史 Bundle：重新 deploy 目标 hash（不重建）。"""
    target = registry.get_production_bundle(to_bundle_hash)
    if target.status not in ("APPROVED", "DEPLOYED", "PAUSED", "RETIRED"):
        raise StateTransitionError(
            f"rollback target status={target.status} not eligible"
        )
    # RETIRED / 旧版：提升回 DEPLOYED
    if target.status == "RETIRED":
        writer.update_status(to_bundle_hash, "APPROVED")
        target = registry.get_production_bundle(to_bundle_hash)
    if target.status != "APPROVED" and target.status != "DEPLOYED":
        if target.status == "PAUSED":
            pass
        else:
            writer.update_status(to_bundle_hash, "APPROVED")
            target = registry.get_production_bundle(to_bundle_hash)
    # 确保 strategy_code 一致
    code = strategy_code or target.strategy_code
    if target.strategy_code and target.strategy_code != code:
        raise StateTransitionError("strategy_code mismatch on rollback")
    target = target.model_copy(update={"strategy_code": code})
    return deploy_bundle(registry, writer, target)
