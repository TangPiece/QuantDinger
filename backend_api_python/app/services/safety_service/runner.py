"""SafetyService：decide / Kill Switch / acknowledge / resume 编排。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from app.services.research_data.registry import ResearchRegistry

from .artifact_store import SafetyArtifactStore
from .cycle import run_decide
from .evaluate import evaluate
from .gate import SafetyGate
from .kill_switch import KillSwitchStore, make_emergency_stop
from .protocol import (
    EmergencyStopIntent,
    SafetyContext,
    SafetyRule,
    SafetyScope,
    SafetyState,
    TradingGateDecision,
)
from .rate_limiter import OrderRateLimiter
from .rules.config import RuleConfigError, merge_rules, validate_rule_against_hard
from .sources import InMemoryMarketDataFreshness, SourceFlags
from .state_machine import SafetyStateError, acknowledge_state, resume_state, transition
from .writers import SafetyWriter


class SafetyError(RuntimeError):
    """Safety 编排错误。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SafetyService:
    """Phase 6G 主入口：OMS submit 前 Fail-Closed 决策。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        portfolio_service: Any = None,
        oms_service: Any = None,
        artifact_store: SafetyArtifactStore | None = None,
        broker_port: Any = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._portfolio = portfolio_service
        self._oms = oms_service
        self._broker = broker_port
        self._writer = SafetyWriter(registry, artifact_store=artifact_store)
        self._kill = KillSwitchStore(repository=self._writer)
        self._rate = OrderRateLimiter()
        self._sources = SourceFlags()
        self._market_data: Any = InMemoryMarketDataFreshness()
        self._rules = merge_rules(self._load_rules_from_registry())
        self._gate = SafetyGate(self)

    @property
    def gate(self) -> SafetyGate:
        """供 OMS.set_trading_gate 注入。"""
        return self._gate

    def set_oms_service(self, oms_service: Any) -> None:
        """延迟注入 OMS（open/pending 数量用于 Position 规则）。"""
        self._oms = oms_service

    def set_market_data_age(self, instrument_key: str, age_sec: float) -> None:
        """测试/故障注入：设置行情陈旧秒数。"""
        if isinstance(self._market_data, InMemoryMarketDataFreshness):
            self._market_data.set_age(instrument_key, age_sec)
        elif hasattr(self._market_data, "set_age"):
            self._market_data.set_age(instrument_key, age_sec)

    def set_market_data_port(self, port: Any) -> None:
        """注入 MarketDataFreshnessPort。"""
        self._market_data = port

    def set_broker_port(self, port: Any) -> None:
        self._broker = port

    @property
    def source_flags(self) -> SourceFlags:
        """只读：外部源标志（Recon CRITICAL 等）。"""
        return self._sources

    def _load_rules_from_registry(self) -> list[SafetyRule] | None:
        try:
            rows = self._registry.list_safety_rules()
        except Exception:
            return None
        if not rows:
            return None
        return [
            SafetyRule(
                rule_id=r.rule_id,
                enabled=bool(r.enabled),
                threshold=float(r.threshold),
                action=r.action,  # type: ignore[arg-type]
                scope=r.scope,  # type: ignore[arg-type]
                metadata=dict(r.metadata or {}),
            )
            for r in rows
        ]

    def _load_states(
        self, account_id: str, strategy_id: str = ""
    ) -> list[SafetyState]:
        states: list[SafetyState] = []
        for scope, sid in (
            ("GLOBAL", "GLOBAL"),
            ("ACCOUNT", account_id),
            ("STRATEGY", strategy_id or ""),
        ):
            if not sid and scope == "STRATEGY":
                continue
            try:
                states.append(self._writer.get_state(scope, sid))
            except KeyError:
                pass
        return states

    def _get_or_create_state(self, scope: str, scope_id: str) -> SafetyState:
        try:
            return self._writer.get_state(scope, scope_id)
        except KeyError:
            return SafetyState(
                scope=scope,  # type: ignore[arg-type]
                scope_id=scope_id,
                state="NORMAL",
            )

    def decide(
        self,
        account_id: str,
        intent: Any = None,
        *,
        strategy_id: str = "",
        prices: Mapping[str, float] | None = None,
        context: SafetyContext | None = None,
        inject: Mapping[str, Any] | None = None,
    ) -> TradingGateDecision:
        """聚合规则 + Kill Switch；阻断时写 Registry 状态/事件。"""
        if context is not None:
            states = self._load_states(account_id, strategy_id)
            decision = evaluate(
                context,
                rules=self._rules,
                states=states,
                kill_switches=self._kill,
                rate_limiter=self._rate,
            )
            if intent is not None and decision.decision == "ALLOW":
                self._rate.record(account_id, strategy_id=strategy_id)
            if decision.decision != "ALLOW":
                from .cycle import _persist_block

                _persist_block(self._writer, decision=decision, ctx=context)
            return decision

        return run_decide(
            account_id,
            intent,
            strategy_id=strategy_id,
            prices=prices,
            writer=self._writer,
            kill_switches=self._kill,
            rate_limiter=self._rate,
            source_flags=self._sources,
            portfolio_service=self._portfolio,
            oms_service=self._oms,
            broker_port=self._broker,
            market_data=self._market_data,
            rules=self._rules,
            inject=inject,
        )

    def is_blocked(self, account_id: str, *, strategy_id: str = "") -> bool:
        """Fail-Closed：decision != ALLOW。"""
        return self._gate.is_blocked(account_id, strategy_id=strategy_id)

    def engage_kill_switch(
        self,
        scope: SafetyScope | str,
        scope_id: str,
        *,
        reason: str = "",
        operator: str = "",
    ) -> TradingGateDecision:
        """Engage Kill Switch 并持久化 HALT/EMERGENCY 状态。"""
        self._kill.engage(
            scope, scope_id, reason=reason, operator=operator
        )
        target = "EMERGENCY" if str(scope).upper() == "GLOBAL" else "HALTED"
        st = self._get_or_create_state(str(scope), scope_id)
        new_st = transition(st, target, reason=reason or "kill switch engaged")  # type: ignore[arg-type]
        self._writer.set_state(new_st)
        decision = "EMERGENCY" if target == "EMERGENCY" else "HALT"
        return TradingGateDecision(
            decision=decision,  # type: ignore[arg-type]
            scope=str(scope),  # type: ignore[arg-type]
            scope_id=scope_id,
            rule_ids=["KILL_SWITCH"],
            reason=reason or f"kill switch engaged ({scope})",
        )

    def disengage_kill_switch(
        self,
        scope: SafetyScope | str,
        scope_id: str,
        *,
        operator: str = "",
        acknowledged: bool = False,
    ) -> None:
        """GLOBAL engaged 需 acknowledged=True 或状态已 acknowledge。"""
        cur = self._kill.get(scope, scope_id)
        if cur.engaged and str(scope).upper() == "GLOBAL" and not acknowledged:
            st = self._get_or_create_state(str(scope), scope_id)
            if not st.acknowledged:
                raise SafetyStateError(
                    "GLOBAL kill switch disengage requires acknowledge"
                )
        self._kill.disengage(
            scope, scope_id, operator=operator, acknowledged=acknowledged
        )

    def acknowledge(self, target: str, *, operator: str = "") -> None:
        """event_id 或 ``SCOPE|scope_id``：标记事件/状态已确认。"""
        key = str(target or "").strip()
        if not key:
            raise SafetyError("acknowledge target required")

        # 优先按 event_id
        try:
            ev = self._writer.get_event(key)
            updated = ev.model_copy(
                update={
                    "acknowledged": True,
                    "operator": operator or ev.operator,
                }
            )
            self._writer.write_event(updated)
            st = self._get_or_create_state(str(ev.scope), ev.scope_id)
            self._writer.set_state(acknowledge_state(st, operator=operator))
            return
        except KeyError:
            pass

        if "|" in key:
            scope, scope_id = key.split("|", 1)
        else:
            raise SafetyError(f"unknown acknowledge target: {target!r}")

        st = self._get_or_create_state(scope, scope_id)
        self._writer.set_state(acknowledge_state(st, operator=operator))

    def resume(
        self,
        scope: SafetyScope | str,
        scope_id: str,
        *,
        operator: str = "",
    ) -> SafetyState:
        """人工恢复 NORMAL；HALT/EMERGENCY 须先 acknowledge。"""
        if str(scope).upper() == "ACCOUNT" and scope_id in self._sources.recon_critical_accounts:
            raise SafetyStateError(
                "resume blocked: reconciliation CRITICAL still active"
            )
        st = self._get_or_create_state(str(scope), scope_id)
        new_st = resume_state(st, operator=operator)
        self._writer.set_state(new_st)
        return new_st

    def report_source(
        self,
        kind: str,
        scope: SafetyScope | str,
        scope_id: str,
        *,
        severity: str = "WARNING",
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        """6F/Broker/Health 等源上报；CRITICAL Recon 写入 SourceFlags。"""
        sk = str(kind or "").upper()
        pay = dict(payload or {})
        sev = str(severity or "").upper()
        acct = scope_id
        if str(scope).upper() == "ACCOUNT":
            acct = scope_id
        elif pay.get("account_id"):
            acct = str(pay["account_id"])

        if sk == "RECONCILIATION_CRITICAL":
            if acct:
                self._sources.set_recon_critical(str(acct), sev == "CRITICAL")
        elif sk == "BROKER_DISCONNECT":
            if self._broker is not None and hasattr(self._broker, "set_connected"):
                self._broker.set_connected(sev != "CRITICAL")
        elif sk == "STRATEGY_ERROR":
            sid = scope_id or str(pay.get("strategy_id") or "")
            if sid:
                if sev == "CRITICAL":
                    self._sources.bump_strategy_error(sid)
                else:
                    self._sources.reset_strategy_error(sid)
        elif sk == "SYSTEM_HEALTH":
            self._sources.system_healthy = sev not in ("CRITICAL", "ERROR")
        elif sk == "MARKET_DATA_STALE":
            ik = str(pay.get("instrument_key") or "")
            age = float(pay.get("age_sec") or 0)
            if ik:
                self.set_market_data_age(ik, age)
        elif sk == "MANUAL":
            if sev == "CRITICAL" and str(scope).upper() == "GLOBAL":
                self._sources.state_known = True

    def ingest_reconciliation(
        self, account_id: str, *, critical: bool = True
    ) -> None:
        """6F 适配：CRITICAL 对账 → Safety 源。"""
        self.report_source(
            "RECONCILIATION_CRITICAL",
            "ACCOUNT",
            account_id,
            severity="CRITICAL" if critical else "INFO",
        )

    def emergency_stop(
        self,
        scope: SafetyScope | str,
        scope_id: str,
        *,
        reason: str = "",
        operator: str = "",
        cancel_open_orders: bool = True,
    ) -> EmergencyStopIntent:
        """紧急停止 Contract；P0 不自动 FLATTEN/撤单。"""
        intent = make_emergency_stop(
            scope=scope,
            scope_id=scope_id,
            reason=reason or "emergency stop",
            cancel_open_orders=cancel_open_orders,
            salt=operator or "emg",
        )
        self.engage_kill_switch(
            scope,
            scope_id,
            reason=reason or "emergency stop",
            operator=operator,
        )
        return intent

    def upsert_rule(self, rule: SafetyRule) -> SafetyRule:
        """写入规则；不得突破 HardLimits。"""
        try:
            validate_rule_against_hard(rule)
        except RuleConfigError as exc:
            raise SafetyError(str(exc)) from exc
        self._writer.upsert_rule(rule)
        self._rules = merge_rules(self._load_rules_from_registry())
        return rule

    def get_state(self, scope: SafetyScope | str, scope_id: str) -> SafetyState:
        return self._writer.get_state(str(scope), scope_id)

    def list_events(
        self,
        *,
        scope: str = "",
        scope_id: str = "",
        rule: str = "",
    ) -> list:
        return self._writer.list_events(scope=scope, scope_id=scope_id, rule=rule)

    def mark_state_unknown(self, scope: str, scope_id: str) -> None:
        """故障注入：UNKNOWN → Fail-Closed BLOCK。"""
        st = self._get_or_create_state(scope, scope_id)
        self._writer.set_state(
            st.model_copy(
                update={"state": "UNKNOWN", "updated_at": _now(), "reason": "injected unknown"}
            )
        )
        self._sources.state_known = False


__all__ = ["SafetyError", "SafetyService"]
