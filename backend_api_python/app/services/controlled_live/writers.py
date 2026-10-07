"""Phase 7C：Controlled Live → Registry + R2。"""

from __future__ import annotations

from app.services.research_data.contracts import (
    ControlledLiveApprovalSummary,
    ControlledLiveCompareRunSummary,
    ControlledLiveOrderIndexRecord,
    ControlledLiveSessionSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ControlledLiveArtifactStore
from .protocol import (
    ENGINE_VERSION,
    ControlledOrder,
    ControlledSession,
    OperatorApproval,
    ShadowVsRealReport,
)


class ControlledLiveWriter:
    """Session / order / approval / compare 索引。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: ControlledLiveArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or ControlledLiveArtifactStore()

    def write_session(self, session: ControlledSession) -> ControlledLiveSessionSummary:
        rec = ControlledLiveSessionSummary(
            session_id=session.session_id,
            account_id=session.account_id,
            environment=session.environment,
            approved_strategy_id=session.approved_strategy_id,
            dataset_hash=session.dataset_hash,
            model_version=session.model_version,
            strategy_version=session.strategy_version,
            status=session.status,
            order_count=session.order_count,
            engine_version=ENGINE_VERSION,
            metadata={
                **dict(session.metadata or {}),
                "max_orders": session.config.max_orders,
            },
        )
        self._registry.upsert_controlled_live_session(rec)
        return rec

    def write_order_index(
        self, order: ControlledOrder, *, session_id: str = ""
    ) -> ControlledLiveOrderIndexRecord:
        rec = ControlledLiveOrderIndexRecord(
            order_id=order.order_id,
            session_id=session_id or order.session_id,
            client_order_id=order.client_order_id,
            broker_order_id=order.broker_order_id,
            symbol=order.symbol,
            side=order.side,
            status=order.status,
            engine_version=ENGINE_VERSION,
            metadata={"lineage": order.lineage, "quantity": order.quantity},
        )
        self._registry.upsert_controlled_live_order_index(rec)
        return rec

    def write_approval(self, approval: OperatorApproval) -> ControlledLiveApprovalSummary:
        rec = ControlledLiveApprovalSummary(
            approval_id=approval.approval_id,
            session_id=approval.session_id,
            operator_actor=approval.operator_actor,
            approval_token_hash=approval.approval_token_hash,
            scope=approval.scope,
            status=approval.status,
            approved_at=approval.approved_at,
            engine_version=ENGINE_VERSION,
            metadata=dict(approval.metadata or {}),
        )
        self._registry.upsert_controlled_live_approval(rec)
        return rec

    def write_compare_run(self, report: ShadowVsRealReport) -> ControlledLiveCompareRunSummary:
        uri, cs = self._artifacts.write_run_payload(
            account_id=report.account_id,
            run_id=report.run_id,
            payload=report.model_dump(mode="json"),
        )
        rec = ControlledLiveCompareRunSummary(
            run_id=report.run_id,
            account_id=report.account_id,
            storage_uri=uri,
            engine_version=ENGINE_VERSION,
            metadata={"checksum": cs, "order_id": report.order_id},
        )
        self._registry.upsert_controlled_live_compare_run(rec)
        return rec
