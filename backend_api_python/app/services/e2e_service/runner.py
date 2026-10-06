"""Phase 6I：E2EService 主入口。"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional

from app.services.research_data.registry import ResearchRegistry
from app.services.risk_engine.policy import finalize_policy
from app.services.risk_engine.protocol import RiskPolicy

from .artifact_store import E2EArtifactStore
from .hash import derive_run_id
from .modes import assert_config_safe, assert_mode
from .pipeline import build_run_payload, run_scenario_pipeline
from .protocol import (
    ComparisonSummary,
    ConsistencyScore,
    ReplayRequest,
    ReplayResult,
    ScenarioResult,
    TradingSession,
)
from .replay import run_replay
from .score import compute_consistency_score
from .scenarios import ALL_SCENARIO_IDS, get_scenario, list_scenarios
from .session import attach_scenario_run, close_session, start_session
from .writers import E2EWriter


class E2EError(RuntimeError):
    """E2E 服务错误。"""


class E2EService:
    """Paper / Shadow 端到端编排；不替代 6C/6G/6F。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        portfolio_service: Any,
        risk_service: Any,
        oms_service: Any,
        safety_service: Any,
        recon_service: Any,
        ops_service: Any,
        artifact_store: E2EArtifactStore | None = None,
        default_policy: RiskPolicy | None = None,
        prices: Mapping[str, float] | None = None,
        broker_adapter: Any = None,
        broker_conn: Any = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._writer = E2EWriter(registry, artifact_store=artifact_store)
        self._services = {
            "portfolio": portfolio_service,
            "risk": risk_service,
            "oms": oms_service,
            "safety": safety_service,
            "recon": recon_service,
            "ops": ops_service,
            "broker_adapter": broker_adapter,
            "broker_conn": broker_conn,
            "default_policy": default_policy
            or finalize_policy(
                RiskPolicy(
                    policy_code="e2e_default",
                    policy_version="1",
                    max_single_position_weight=0.50,
                    max_gross_exposure=1.0,
                    max_turnover=1.0,
                    max_position_delta_weight=0.50,
                    clip_on_limit=True,
                )
            ),
        }
        self._prices = dict(prices or {"USStock:AAPL": 100.0})
        self._session: TradingSession | None = None

    def _reset_broker_sim(self) -> None:
        """场景间清 Simulated 内存簿，避免订单/持仓泄漏。"""
        adapter = self._services.get("broker_adapter")
        if adapter is None:
            return
        book = getattr(adapter, "_rest", None)
        if book is not None:
            book._orders.clear()
            book._executions.clear()
            book._event_seq = 0
        if hasattr(adapter, "_positions") and isinstance(adapter._positions, dict):
            adapter._positions.clear()
        deduper = getattr(adapter, "_deduper", None)
        if deduper is not None and hasattr(deduper, "_seen"):
            deduper._seen.clear()
        if hasattr(adapter, "connect"):
            try:
                adapter.connect()
            except Exception:
                pass
        conn = self._services.get("broker_conn")
        if conn is not None and hasattr(conn, "set_connected"):
            conn.set_connected(True)

    def _account_ctx(self) -> tuple[str, str]:
        if self._session and self._session.account_id and self._session.portfolio_id:
            return self._session.account_id, self._session.portfolio_id
        raise E2EError("no active session with account; call start_session first")

    def start_session(
        self,
        *,
        trading_date: str | None = None,
        market: str = "US",
        mode: str = "PAPER",
        dataset_hash: str = "e2e_dh_v1",
        strategy_version: str = "e2e_sv_v1",
        strategy_id: str = "e2e_strategy",
        initial_cash: float = 1_000_000.0,
        salt: str = "",
    ) -> TradingSession:
        """打开账户 + TradingSession。"""
        m = assert_mode(mode)
        td = trading_date or date.today().isoformat()
        env = "PAPER" if m != "SHADOW" else "SHADOW"
        acct = self._services["portfolio"].open_account(
            environment=env,
            market="US",
            initial_cash=initial_cash,
        )
        pid = acct.metadata["default_portfolio_id"]
        session = start_session(
            self._writer,
            trading_date=td,
            market=market,
            mode=m,
            dataset_hash=dataset_hash,
            strategy_version=strategy_version,
            strategy_id=strategy_id,
            account_id=acct.account_id,
            portfolio_id=pid,
            salt=salt,
        )
        self._session = session
        return session

    def close_session(self, session_id: str | None = None) -> TradingSession:
        sid = session_id or (self._session.session_id if self._session else "")
        if not sid:
            raise E2EError("session_id required")
        closed = close_session(self._writer, sid)
        if self._session and self._session.session_id == sid:
            self._session = closed
        return closed

    def get_session(self, session_id: str) -> TradingSession:
        return self._writer.get_session(session_id)

    def run_scenario(
        self,
        scenario_id: str,
        *,
        mode: str = "PAPER",
        run_id: str = "",
        salt: str = "",
    ) -> ScenarioResult:
        """运行单个 E2E 场景。"""
        m = assert_mode(mode)
        self._reset_broker_sim()
        spec = get_scenario(scenario_id)
        session = self._session
        if session is None:
            session = self.start_session(mode=m, salt=salt or scenario_id)
        aid, pid = session.account_id, session.portfolio_id
        rid = run_id or derive_run_id(
            session_id=session.session_id, scenario_id=scenario_id, salt=salt
        )
        result = run_scenario_pipeline(
            spec,
            mode=m,
            services=self._services,
            session_id=session.session_id,
            run_id=rid,
            account_id=aid,
            portfolio_id=pid,
            prices=self._prices,
            dataset_hash=session.dataset_hash,
            strategy_version=session.strategy_version,
            strategy_id=session.strategy_id,
            salt=salt or spec.fixture_id,
        )
        if result.virtual_orders:
            self._writer.write_virtual_orders(result.virtual_orders)
        payload = build_run_payload(result, [])
        self._writer.write_scenario_result(result, payload=payload)
        attach_scenario_run(self._writer, session.session_id, result.scenario_run_id)
        return result

    def run_suite(
        self,
        *,
        mode: str = "PAPER",
        salt: str = "suite",
    ) -> list[ScenarioResult]:
        """顺序运行 E2E-001 … E2E-010（每场景独立 session salt）。"""
        m = assert_mode(mode)
        out: list[ScenarioResult] = []
        for sid in ALL_SCENARIO_IDS:
            self._session = None
            self.start_session(mode=m, salt=f"{salt}|{sid}")
            out.append(self.run_scenario(sid, mode=m, salt=f"{salt}|{sid}"))
        return out

    def replay(self, request: ReplayRequest) -> ReplayResult:
        """同 fixture 双跑比对 intent 指纹。"""
        assert_config_safe(request.config)

        def _once(spec, dh: str) -> str:
            self._session = None
            self.start_session(
                mode=request.mode,
                dataset_hash=dh,
                strategy_version=request.strategy_version,
                salt=f"replay|{request.fixture_id}",
            )
            r = self.run_scenario(
                request.scenario_id,
                mode=request.mode,
                salt=f"replay|{request.fixture_id}|{dh}",
            )
            return r.intent_fingerprint

        return run_replay(
            request,
            run_once=_once,
            get_spec=get_scenario,
        )

    def consistency_score(self, run_id: str) -> ConsistencyScore:
        """按 run_id 聚合已持久化场景 run。"""
        rows = self._writer.list_scenario_runs(run_id=run_id)
        results = [
            ScenarioResult(
                scenario_run_id=r.scenario_run_id,
                scenario_id=r.scenario_id,
                run_id=r.run_id,
                session_id=r.session_id,
                mode=r.mode,  # type: ignore[arg-type]
                status=r.status,  # type: ignore[arg-type]
                trace_id=r.trace_id,
                dataset_hash=r.dataset_hash,
                strategy_version=r.strategy_version,
                intent_fingerprint=r.intent_fingerprint,
                metadata=dict(r.metadata or {}),
            )
            for r in rows
        ]
        session_id = results[0].session_id if results else ""
        audit_n = len(
            self._services["ops"].list_audit_events(limit=500)
        )
        score = compute_consistency_score(
            results,
            run_id=run_id,
            session_id=session_id,
            audit_event_count=audit_n,
        )
        self._writer.write_consistency_score(score)
        return score

    def shadow_compare(
        self,
        paper_run_id: str,
        shadow_run_id: str,
        *,
        scenario_id: str = "",
    ) -> ComparisonSummary:
        """Paper vs Shadow intent 指纹对比（按 scenario_id 对齐）。"""
        paper = self._writer.list_scenario_runs(run_id=paper_run_id)
        shadow = self._writer.list_scenario_runs(run_id=shadow_run_id)
        if scenario_id:
            paper = [r for r in paper if r.scenario_id == scenario_id]
            shadow = [r for r in shadow if r.scenario_id == scenario_id]
        pf = {r.scenario_id: r.intent_fingerprint for r in paper}
        sf = {r.scenario_id: r.intent_fingerprint for r in shadow}
        match = pf == sf and bool(pf)
        virtual_n = sum(
            len(self._registry.list_e2e_virtual_orders(session_id=r.session_id))
            for r in shadow
        )
        return ComparisonSummary(
            paper_run_id=paper_run_id,
            shadow_run_id=shadow_run_id,
            intent_match=match,
            target_count_paper=len(paper),
            target_count_shadow=len(shadow),
            virtual_order_count=virtual_n,
            messages=[] if match else ["intent fingerprint mismatch between modes"],
        )


__all__ = ["E2EError", "E2EService", "list_scenarios"]
