"""Reconciliation Run/Finding/Gate/Cursor → Registry。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.research_data.contracts import (
    BrokerSnapshotIndexRecord,
    ReconciliationCursorRecord,
    ReconciliationFindingSummary,
    ReconciliationGateRecord,
    ReconciliationRunSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ReconciliationArtifactStore
from .protocol import (
    ENGINE_VERSION,
    BrokerSnapshot,
    GateState,
    ReconciliationCursor,
    ReconciliationFinding,
    ReconciliationRun,
)


class ReconciliationWriter:
    """持久化 6F 索引与 Snapshot 明细。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: ReconciliationArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or ReconciliationArtifactStore()

    def write_run(self, run: ReconciliationRun) -> ReconciliationRunSummary:
        summary = ReconciliationRunSummary(
            run_id=run.run_id,
            account_id=run.account_id,
            portfolio_id=run.portfolio_id,
            broker_id=run.broker_id,
            mode=str(run.mode),
            started_at=run.started_at,
            completed_at=run.completed_at,
            snapshot_id=run.snapshot_id,
            finding_count=run.finding_count,
            critical_count=run.critical_count,
            gate_blocked=run.gate_blocked,
            engine_version=run.engine_version or ENGINE_VERSION,
            metadata=dict(run.metadata or {}),
        )
        self._registry.upsert_reconciliation_run(summary)
        return summary

    def write_finding(
        self, finding: ReconciliationFinding
    ) -> ReconciliationFindingSummary:
        summary = ReconciliationFindingSummary(
            finding_id=finding.finding_id,
            run_id=finding.run_id,
            type=str(finding.type),
            severity=str(finding.severity),
            status=str(finding.status),
            entity_type=str(finding.entity_type),
            entity_id=finding.entity_id,
            expected=dict(finding.expected or {}),
            actual=dict(finding.actual or {}),
            difference=dict(finding.difference or {}),
            detected_at=finding.detected_at,
            resolved_at=finding.resolved_at,
            metadata=dict(finding.metadata or {}),
        )
        self._registry.upsert_reconciliation_finding(summary)
        return summary

    def write_snapshot(self, snapshot: BrokerSnapshot) -> BrokerSnapshotIndexRecord:
        uri, cs = self._artifacts.write_snapshot(snapshot)
        snapshot = snapshot.model_copy(update={"raw_storage_uri": uri})
        rec = BrokerSnapshotIndexRecord(
            snapshot_id=snapshot.snapshot_id,
            broker_id=snapshot.broker_id,
            account_id=snapshot.account_id,
            captured_at=snapshot.captured_at,
            storage_uri=uri,
            checksum=cs,
            metadata=dict(snapshot.metadata or {}),
        )
        self._registry.append_broker_snapshot_index(rec)
        return rec

    def set_gate(self, state: GateState) -> ReconciliationGateRecord:
        rec = ReconciliationGateRecord(
            account_id=state.account_id,
            blocked=state.blocked,
            reason=state.reason,
            finding_id=state.finding_id,
            updated_at=state.updated_at
            or datetime.now(timezone.utc).isoformat(),
            metadata=dict(state.metadata or {}),
        )
        self._registry.set_reconciliation_gate(rec)
        return rec

    def get_gate(self, account_id: str) -> GateState:
        rec = self._registry.get_reconciliation_gate(account_id)
        return GateState(
            account_id=rec.account_id,
            blocked=bool(rec.blocked),
            reason=rec.reason,
            finding_id=rec.finding_id,
            updated_at=rec.updated_at,
            metadata=dict(rec.metadata or {}),
        )

    def set_cursor(self, cursor: ReconciliationCursor) -> ReconciliationCursorRecord:
        rec = ReconciliationCursorRecord(
            account_id=cursor.account_id,
            broker_id=cursor.broker_id,
            cursor_type=str(cursor.cursor_type),
            cursor_value=cursor.cursor_value,
            updated_at=cursor.updated_at
            or datetime.now(timezone.utc).isoformat(),
        )
        self._registry.set_reconciliation_cursor(rec)
        return rec

    def get_cursor(
        self,
        account_id: str,
        *,
        broker_id: str = "",
        cursor_type: str = "EXECUTION",
    ) -> ReconciliationCursor:
        rec = self._registry.get_reconciliation_cursor(
            account_id, broker_id=broker_id, cursor_type=cursor_type
        )
        return ReconciliationCursor(
            account_id=rec.account_id,
            broker_id=rec.broker_id,
            cursor_type=rec.cursor_type,  # type: ignore[arg-type]
            cursor_value=rec.cursor_value,
            updated_at=rec.updated_at,
        )

    def list_findings(
        self,
        *,
        run_id: str = "",
        account_id: str = "",
        status: str = "",
    ) -> list[ReconciliationFinding]:
        rows = self._registry.list_reconciliation_findings(
            run_id=run_id, account_id=account_id, status=status
        )
        return [
            ReconciliationFinding(
                finding_id=r.finding_id,
                run_id=r.run_id,
                type=r.type,  # type: ignore[arg-type]
                severity=r.severity,  # type: ignore[arg-type]
                status=r.status,  # type: ignore[arg-type]
                entity_type=r.entity_type,  # type: ignore[arg-type]
                entity_id=r.entity_id,
                expected=dict(r.expected or {}),
                actual=dict(r.actual or {}),
                difference=dict(r.difference or {}),
                detected_at=r.detected_at,
                resolved_at=r.resolved_at,
                metadata=dict(r.metadata or {}),
            )
            for r in rows
        ]

    def get_finding(self, finding_id: str) -> ReconciliationFinding:
        for r in self._registry.list_reconciliation_findings():
            if r.finding_id == finding_id:
                return ReconciliationFinding(
                    finding_id=r.finding_id,
                    run_id=r.run_id,
                    type=r.type,  # type: ignore[arg-type]
                    severity=r.severity,  # type: ignore[arg-type]
                    status=r.status,  # type: ignore[arg-type]
                    entity_type=r.entity_type,  # type: ignore[arg-type]
                    entity_id=r.entity_id,
                    expected=dict(r.expected or {}),
                    actual=dict(r.actual or {}),
                    difference=dict(r.difference or {}),
                    detected_at=r.detected_at,
                    resolved_at=r.resolved_at,
                    metadata=dict(r.metadata or {}),
                )
        raise KeyError(f"finding not found: {finding_id!r}")
