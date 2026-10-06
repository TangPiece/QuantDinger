"""Phase 6I：E2E → Registry + R2。"""

from __future__ import annotations

from app.services.research_data.contracts import (
    E2EConsistencyScoreRecord,
    E2EScenarioRunSummary,
    E2ESessionSummary,
    E2EVirtualOrderSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import E2EArtifactStore
from .protocol import (
    ENGINE_VERSION,
    ConsistencyScore,
    E2ERunPayload,
    ScenarioResult,
    TradingSession,
    VirtualOrder,
)


class E2EWriter:
    """场景运行 / Session / Score / VirtualOrder 持久化。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: E2EArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifacts = artifact_store or E2EArtifactStore()

    def write_scenario_result(
        self,
        result: ScenarioResult,
        *,
        payload: E2ERunPayload | None = None,
    ) -> E2EScenarioRunSummary:
        meta = dict(result.metadata or {})
        if payload is not None and result.session_id and result.run_id:
            uri, cs = self._artifacts.write_run_payload(
                payload,
                session_id=result.session_id,
                run_id=result.scenario_run_id,
            )
            meta["storage_uri"] = uri
            meta["checksum"] = cs
        summary = E2EScenarioRunSummary(
            scenario_run_id=result.scenario_run_id,
            scenario_id=result.scenario_id,
            run_id=result.run_id,
            session_id=result.session_id,
            mode=str(result.mode),
            status=result.status,
            trace_id=result.trace_id,
            dataset_hash=result.dataset_hash,
            strategy_version=result.strategy_version,
            strategy_id=result.strategy_id,
            intent_fingerprint=result.intent_fingerprint,
            engine_version=ENGINE_VERSION,
            metadata=meta,
        )
        self._registry.upsert_e2e_scenario_run(summary)
        return summary

    def write_session(self, session: TradingSession) -> E2ESessionSummary:
        rec = E2ESessionSummary(
            session_id=session.session_id,
            trading_date=session.trading_date,
            market=session.market,
            mode=str(session.mode),
            status=session.status,
            account_id=session.account_id,
            portfolio_id=session.portfolio_id,
            dataset_hash=session.dataset_hash,
            strategy_version=session.strategy_version,
            strategy_id=session.strategy_id,
            opened_at=session.opened_at,
            closed_at=session.closed_at,
            engine_version=session.engine_version,
            metadata={
                **dict(session.metadata or {}),
                "scenario_run_ids": list(session.scenario_run_ids),
            },
        )
        self._registry.upsert_e2e_session(rec)
        return rec

    def get_session(self, session_id: str) -> TradingSession:
        rec = self._registry.get_e2e_session(session_id)
        meta = dict(rec.metadata or {})
        runs = meta.pop("scenario_run_ids", [])
        return TradingSession(
            session_id=rec.session_id,
            trading_date=rec.trading_date,
            market=rec.market,
            mode=rec.mode,  # type: ignore[arg-type]
            status=rec.status,  # type: ignore[arg-type]
            account_id=rec.account_id,
            portfolio_id=rec.portfolio_id,
            dataset_hash=rec.dataset_hash,
            strategy_version=rec.strategy_version,
            strategy_id=rec.strategy_id,
            opened_at=rec.opened_at,
            closed_at=rec.closed_at,
            scenario_run_ids=list(runs or []),
            engine_version=rec.engine_version,
            metadata=meta,
        )

    def write_consistency_score(self, score: ConsistencyScore) -> E2EConsistencyScoreRecord:
        rec = E2EConsistencyScoreRecord(
            score_id=score.score_id,
            run_id=score.run_id,
            session_id=score.session_id,
            signal_consistency=float(score.signal_consistency),
            order_consistency=float(score.order_consistency),
            execution_consistency=float(score.execution_consistency),
            position_consistency=float(score.position_consistency),
            reconciliation_score=float(score.reconciliation_score),
            audit_coverage=float(score.audit_coverage),
            safety_coverage=float(score.safety_coverage),
            overall=float(score.overall),
            engine_version=score.engine_version,
            metadata=dict(score.metadata or {}),
        )
        self._registry.upsert_e2e_consistency_score(rec)
        return rec

    def write_virtual_orders(
        self, orders: list[VirtualOrder]
    ) -> list[E2EVirtualOrderSummary]:
        out: list[E2EVirtualOrderSummary] = []
        for vo in orders:
            rec = E2EVirtualOrderSummary(
                virtual_order_id=vo.virtual_order_id,
                session_id=vo.session_id,
                scenario_run_id=vo.scenario_run_id,
                trace_id=vo.trace_id,
                instrument_key=vo.instrument_key,
                side=vo.side,
                quantity=float(vo.quantity),
                status=vo.status,
                created_at=vo.created_at,
                metadata=dict(vo.metadata or {}),
            )
            self._registry.upsert_e2e_virtual_order(rec)
            out.append(rec)
        return out

    def list_scenario_runs(self, **kwargs):
        return self._registry.list_e2e_scenario_runs(**kwargs)
