"""Phase 6J：ReadinessService 主入口。"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional

from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ReadinessArtifactStore
from .checklist import CHECK_SCENARIO_MAP, aggregate_checklist
from .faults import get_fault_case, list_fault_cases, list_slos, run_fault
from .hash import derive_readiness_run_id
from .modes import assert_mode
from .pipeline import run_scenario_pipeline
from .protocol import (
    ChecklistResult,
    FaultResult,
    ReadinessCheck,
    ScenarioResult,
    TradingSLO,
)
from .recover import orchestrate_recover_on_start
from .scenarios import ALL_SCENARIO_IDS, get_scenario, list_scenarios
from .writers import ReadinessWriter

from app.services.oms.protocol import RecoverReport


class ReadinessError(RuntimeError):
    """Readiness 服务错误。"""


class ReadinessService:
    """生产就绪验收 harness；禁止 LIVE。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        oms_service: Any,
        safety_service: Any,
        recon_service: Any,
        ops_service: Any,
        portfolio_service: Any,
        risk_service: Any,
        e2e_service: Any = None,
        broker_adapter: Any = None,
        broker_adapter_service: Any = None,
        artifact_store: ReadinessArtifactStore | None = None,
        prices: Mapping[str, float] | None = None,
        registry_root: Any = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._writer = ReadinessWriter(registry, artifact_store=artifact_store)
        self._registry_root = registry_root
        self._prices = dict(prices or {"USStock:AAPL": 100.0})
        self._services = {
            "portfolio": portfolio_service,
            "risk": risk_service,
            "oms": oms_service,
            "safety": safety_service,
            "recon": recon_service,
            "ops": ops_service,
            "e2e": e2e_service,
            "broker_adapter": broker_adapter,
            "broker_adapter_service": broker_adapter_service,
        }
        self._account_id = ""
        self._portfolio_id = ""

    def _reset_safety_kills(self) -> None:
        """场景/套件间清除 Kill Switch + HALT 状态。"""
        safety = self._services["safety"]
        pairs = (
            ("STRATEGY", "rdy_strategy"),
            ("STRATEGY", "rdy_other_strategy"),
            ("ACCOUNT", self._account_id),
            ("GLOBAL", "GLOBAL"),
        )
        for scope, sid in pairs:
            if not sid:
                continue
            key = f"{scope}|{sid}"
            try:
                safety.acknowledge(key, operator="rdy_reset")
            except Exception:
                pass
            try:
                safety.resume(str(scope), str(sid), operator="rdy_reset")
            except Exception:
                pass
            try:
                safety.disengage_kill_switch(
                    str(scope),
                    str(sid),
                    operator="rdy_reset",
                    acknowledged=True,
                )
            except Exception:
                pass

    def _reset_broker_sim(self) -> None:
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

    def _ensure_account(self, *, salt: str = "") -> tuple[str, str]:
        if self._account_id and self._portfolio_id:
            return self._account_id, self._portfolio_id
        acct = self._services["portfolio"].open_account(
            environment="PAPER",
            market="US",
            initial_cash=1_000_000.0,
        )
        pid = acct.metadata["default_portfolio_id"]
        self._account_id = acct.account_id
        self._portfolio_id = pid
        return acct.account_id, pid

    def recover_on_start(self, *, account_id: str = "") -> RecoverReport:
        return orchestrate_recover_on_start(
            self._services["oms"],
            account_id=account_id or self._account_id,
            recon_service=self._services["recon"],
        )

    def run_scenario(
        self,
        scenario_id: str,
        *,
        run_id: str = "",
        salt: str = "",
    ) -> ScenarioResult:
        # 场景间隔离：新账户 + 清 Simulated 簿，避免 Kill/持仓泄漏
        self._account_id = ""
        self._portfolio_id = ""
        self._reset_broker_sim()
        self._reset_safety_kills()
        spec = get_scenario(scenario_id)
        aid, pid = self._ensure_account(salt=salt or scenario_id)
        rid = run_id or derive_readiness_run_id(salt=salt or scenario_id)
        result = run_scenario_pipeline(
            spec,
            services=self._services,
            run_id=rid,
            account_id=aid,
            portfolio_id=pid,
            trading_date=date.today().isoformat(),
            prices=self._prices,
            salt=salt or spec.fixture_id,
            registry_root=self._registry_root,
        )
        self._writer.write_scenario_result(result, run_id=rid)
        return result

    def run_check(self, check_id: str) -> ReadinessCheck:
        cid = str(check_id or "").strip().lower()
        scenario_id = CHECK_SCENARIO_MAP.get(cid)
        if not scenario_id:
            raise ReadinessError(f"unknown check_id: {check_id!r}")
        sr = self.run_scenario(scenario_id, salt=cid)
        return ReadinessCheck(
            check_id=cid,
            scenario_id=scenario_id,
            status=sr.status,
            messages=list(sr.messages),
            metadata=dict(sr.metadata or {}),
        )

    def run_checklist(self, *, salt: str = "checklist") -> ChecklistResult:
        assert_mode("PAPER")
        run_id = derive_readiness_run_id(salt=salt)
        results: dict[str, ScenarioResult] = {}
        for sid in ALL_SCENARIO_IDS:
            results[sid] = self.run_scenario(sid, run_id=run_id, salt=f"{salt}|{sid}")
        checklist = aggregate_checklist(results, salt=salt)
        self._writer.write_checklist(checklist)
        self._reset_safety_kills()
        return checklist

    def run_fault(self, fault_id: str) -> FaultResult:
        return run_fault(
            fault_id,
            run_scenario=lambda sid: self.run_scenario(sid, salt=f"fault|{fault_id}"),
        )

    def list_slos(self) -> list[TradingSLO]:
        return list_slos()

    def list_scenarios(self):
        return list_scenarios()

    def list_faults(self):
        return list_fault_cases()
