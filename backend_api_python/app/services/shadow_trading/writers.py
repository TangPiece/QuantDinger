"""Phase 7B：Shadow → Registry + R2。"""

from __future__ import annotations

from app.services.research_data.contracts import (
    ShadowCompareRunSummary,
    ShadowExecutionIndexRecord,
    ShadowOrderIndexRecord,
    ShadowSessionSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ShadowArtifactStore
from .protocol import ENGINE_VERSION, ShadowCompareReport, ShadowExecution, ShadowOrder, ShadowSession


class ShadowWriter:
    """Session / order / execution / compare 索引。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: ShadowArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or ShadowArtifactStore()

    def write_session(self, session: ShadowSession) -> ShadowSessionSummary:
        rec = ShadowSessionSummary(
            session_id=session.session_id,
            account_id=session.account_id,
            environment=session.environment,
            dataset_hash=session.dataset_hash,
            model_version=session.model_version,
            strategy_version=session.strategy_version,
            status=session.status,
            engine_version=ENGINE_VERSION,
            metadata=dict(session.metadata or {}),
        )
        self._registry.upsert_shadow_session(rec)
        return rec

    def write_order_index(self, order: ShadowOrder, *, session_id: str = "") -> ShadowOrderIndexRecord:
        rec = ShadowOrderIndexRecord(
            order_id=order.order_id,
            session_id=session_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            status=order.status,
            engine_version=ENGINE_VERSION,
            metadata={"quantity": order.quantity, "filled": order.filled_quantity},
        )
        self._registry.upsert_shadow_order_index(rec)
        return rec

    def write_execution_index(
        self, execution: ShadowExecution, *, session_id: str = ""
    ) -> ShadowExecutionIndexRecord:
        rec = ShadowExecutionIndexRecord(
            execution_id=execution.execution_id,
            order_id=execution.order_id,
            session_id=session_id,
            symbol=execution.symbol,
            quantity=execution.quantity,
            price=execution.price,
            engine_version=ENGINE_VERSION,
            metadata={"fee": execution.fee, "slippage_bps": execution.slippage_bps},
        )
        self._registry.upsert_shadow_execution_index(rec)
        return rec

    def write_compare_run(self, report: ShadowCompareReport) -> ShadowCompareRunSummary:
        uri, cs = self._artifacts.write_run_payload(
            account_id=report.account_id,
            run_id=report.run_id,
            payload=report.model_dump(mode="json"),
        )
        rec = ShadowCompareRunSummary(
            run_id=report.run_id,
            account_id=report.account_id,
            storage_uri=uri,
            engine_version=ENGINE_VERSION,
            metadata={"checksum": cs, "finding_count": len(report.findings)},
        )
        self._registry.upsert_shadow_compare_run(rec)
        return rec
