"""Phase 7E：Governance → Registry + R2。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.registry import ResearchRegistry

from .artifact_store import GovernanceArtifactStore
from .protocol import (
    ENGINE_VERSION,
    GovernanceApproval,
    PortfolioTarget,
    ScaleCriteriaReport,
    ScaleState,
    StrategyLifecycleRecord,
    StrategyVersionPin,
)


class GovernanceWriter:
    """索引与 artifact 写入。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: GovernanceArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or GovernanceArtifactStore()

    def write_strategy_version(self, pin: StrategyVersionPin) -> None:
        from app.services.research_data.contracts import GovStrategyVersionSummary

        rec = GovStrategyVersionSummary(
            strategy_id=pin.strategy_id,
            strategy_version=pin.strategy_version,
            model_version=pin.model_version,
            dataset_hash=pin.dataset_hash,
            feature_version=pin.feature_version,
            content_hash=pin.content_hash,
            is_live=pin.is_live,
            engine_version=ENGINE_VERSION,
            metadata=dict(pin.metadata or {}),
        )
        self._registry.upsert_gov_strategy_version(rec)

    def write_lifecycle(self, lc: StrategyLifecycleRecord) -> None:
        from app.services.research_data.contracts import GovStrategyLifecycleSummary

        rec = GovStrategyLifecycleSummary(
            strategy_id=lc.strategy_id,
            state=lc.state,
            active_version=lc.active_version,
            previous_stable_version=lc.previous_stable_version,
            scale_level=lc.scale_level,
            updated_at=lc.updated_at,
            engine_version=ENGINE_VERSION,
            metadata=dict(lc.metadata or {}),
        )
        self._registry.upsert_gov_strategy_lifecycle(rec)

    def write_scale_state(self, st: ScaleState) -> None:
        from app.services.research_data.contracts import GovScaleStateSummary

        rec = GovScaleStateSummary(
            strategy_id=st.strategy_id,
            account_id=st.account_id,
            current_level=st.current_level,
            pending_level=st.pending_level,
            live_env_approved=st.live_env_approved,
            updated_at=st.updated_at,
            engine_version=ENGINE_VERSION,
            metadata=dict(st.metadata or {}),
        )
        self._registry.upsert_gov_scale_state(rec)

    def write_approval(self, appr: GovernanceApproval) -> None:
        from app.services.research_data.contracts import GovScaleApprovalSummary

        rec = GovScaleApprovalSummary(
            approval_id=appr.approval_id,
            kind=appr.kind,
            strategy_id=appr.strategy_id,
            account_id=appr.account_id,
            operator_actor=appr.operator_actor,
            approval_token_hash=appr.approval_token_hash,
            status=appr.status,
            from_scale=appr.from_scale,
            to_scale=appr.to_scale,
            approved_at=appr.approved_at,
            engine_version=ENGINE_VERSION,
            metadata=dict(appr.metadata or {}),
        )
        self._registry.upsert_gov_scale_approval(rec)

    def write_aggregation_run(
        self,
        *,
        account_id: str,
        run_id: str,
        targets: tuple[PortfolioTarget, ...],
    ) -> Any:
        from app.services.research_data.contracts import GovAggregationRunSummary

        payload = {
            "run_id": run_id,
            "account_id": account_id,
            "targets": [t.model_dump(mode="json") for t in targets],
            "engine_version": ENGINE_VERSION,
        }
        uri, cs = self._artifacts.write_payload(
            account_id=account_id,
            artifact_id=run_id,
            payload=payload,
        )
        rec = GovAggregationRunSummary(
            run_id=run_id,
            account_id=account_id,
            storage_uri=uri,
            engine_version=ENGINE_VERSION,
            metadata={"checksum": cs, "target_count": len(targets)},
        )
        self._registry.upsert_gov_aggregation_run(rec)
        return rec
