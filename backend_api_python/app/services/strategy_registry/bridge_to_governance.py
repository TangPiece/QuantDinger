"""Phase 8A：StrategyVersionRecord → 7E gov_strategy_version / active_version。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.research_data.registry import ResearchRegistry

from .identity import strategy_id_from_code
from .protocol import StrategyVersionRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_governance_version_pin(
    registry: ResearchRegistry,
    version: StrategyVersionRecord,
    *,
    is_live: bool = False,
) -> None:
    """将 8A 版本钉扎写入 D1/LocalJson gov_strategy_version 索引。"""
    from app.services.research_data.contracts import GovStrategyVersionSummary
    from app.services.trading_governance.protocol import ENGINE_VERSION as GOV_ENGINE

    sid = strategy_id_from_code(version.strategy_code)
    rec = GovStrategyVersionSummary(
        strategy_id=sid,
        strategy_version=version.strategy_version,
        model_version=version.model_version,
        dataset_hash=version.dataset_hash,
        feature_version=version.feature_version,
        content_hash=version.content_hash,
        is_live=is_live,
        engine_version=GOV_ENGINE,
        metadata={
            "version_id": version.version_id,
            "bundle_hash": version.bundle_hash,
            "strategy_hash": version.strategy_hash,
            "source": version.source,
        },
    )
    registry.upsert_gov_strategy_version(rec)


def write_governance_active_version(
    registry: ResearchRegistry,
    version: StrategyVersionRecord,
    *,
    lifecycle_state: str = "DRAFT",
) -> None:
    """更新 gov_strategy_lifecycle.active_version（不 promote LIVE）。"""
    from app.services.research_data.contracts import GovStrategyLifecycleSummary
    from app.services.trading_governance.protocol import ENGINE_VERSION as GOV_ENGINE

    sid = strategy_id_from_code(version.strategy_code)
    rec = GovStrategyLifecycleSummary(
        strategy_id=sid,
        state=lifecycle_state,
        active_version=version.strategy_version,
        updated_at=_now(),
        engine_version=GOV_ENGINE,
        metadata={"linked_from": "8A", "version_id": version.version_id},
    )
    registry.upsert_gov_strategy_lifecycle(rec)


def link_governance_active(
    registry: ResearchRegistry,
    version: StrategyVersionRecord,
    governance: Any | None = None,
) -> None:
    """同步 7E：版本 pin + lifecycle active_version；可选刷新进程内 Governance。"""
    write_governance_version_pin(registry, version, is_live=False)
    write_governance_active_version(registry, version)
    if governance is None:
        return
    sid = strategy_id_from_code(version.strategy_code)
    if hasattr(governance, "register_strategy_version"):
        governance.register_strategy_version(
            strategy_id=sid,
            strategy_version=version.strategy_version,
            model_version=version.model_version,
            dataset_hash=version.dataset_hash,
            feature_version=version.feature_version,
            is_live=False,
            metadata={"version_id": version.version_id, "linked_from": "8A"},
        )
