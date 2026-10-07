"""Phase 8G：StrategyGuardrailsService 门面（Monitoring 发现 → Guardrail 保护 → Governance 决策）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.services.research_data.registry import ResearchRegistry
from app.services.strategy_registry.identity import strategy_id_from_code

from .action_matrix import lookup_action
from .actions.pause import apply_pause
from .actions.resume import ResumeBlockedError, apply_resume
from .actions.rollback import apply_rollback
from .actions.safety_stop import apply_safety_stop
from .actions.throttle import apply_throttle
from .actions.warn import apply_warn
from .auto_action_policy import is_auto_allowed, reject_auto_reason
from .bridges.monitoring import load_monitoring_context
from .capital_guard import assert_no_capital_reallocation
from .decision import (
    GuardrailDecisionError,
    approve_decision,
    assert_executable,
    new_decision,
)
from .evaluators.from_monitoring import breaches_from_alerts, breaches_from_health_overall
from .evaluators.inject import (
    breaches_from_inject,
    lifecycle_from_inject,
    merge_guardrail_inject,
    recovery_healthy_from_inject,
)
from .identity import build_governance_event_id, normalize_session_id
from .incident import open_incident
from .policy import resolve_guardrail_policies
from .protocol import (
    GovernanceDecision,
    GovernanceEvent,
    GovernanceIncident,
    GuardrailEvaluationResult,
    GuardrailRollbackRecord,
    StrategyRuntimeState,
)
from .runtime_state import load_runtime_state
from .writers import StrategyGuardrailsWriter


class StrategyGuardrailsError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_type_for_action(action: str) -> str:
    mapping = {
        "WARN": "STRATEGY_WARNED",
        "THROTTLE": "STRATEGY_THROTTLED",
        "PAUSE": "STRATEGY_PAUSED",
        "SAFETY_STOP": "SAFETY_STOP_NEW_ORDERS",
        "STOP": "STRATEGY_STOPPED",
        "ROLLBACK": "STRATEGY_ROLLED_BACK",
        "RESUME": "STRATEGY_RESUMED",
    }
    return mapping.get(str(action).upper(), "GUARDRAIL_BREACH")


class StrategyGuardrailsService:
    """Guardrail Engine：evaluate → auto protect / incident / decision。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        monitoring: Any | None = None,
        governance: Any | None = None,
        safety: Any | None = None,
        promotion: Any | None = None,
        writer: StrategyGuardrailsWriter | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._monitoring = monitoring
        self._governance = governance
        self._safety = safety
        self._promotion = promotion
        self._writer = writer or StrategyGuardrailsWriter(registry)

    def evaluate_from_monitoring(
        self,
        strategy_code: str,
        *,
        inject: Mapping[str, Any] | None = None,
        session_id: str = "",
    ) -> GuardrailEvaluationResult:
        code = str(strategy_code or "").strip()
        if not code:
            raise StrategyGuardrailsError("strategy_code required")
        sid = normalize_session_id(session_id)
        ts = _now()

        guard_policy, auto_policy = resolve_guardrail_policies(self._registry)
        self._writer.write_guardrail_policy(guard_policy)
        self._writer.write_auto_action_policy(auto_policy)

        section = merge_guardrail_inject(inject)
        lifecycle = lifecycle_from_inject(section)
        if lifecycle == "UNKNOWN" and self._governance is not None:
            sid_gov = strategy_id_from_code(code)
            lc = getattr(self._governance, "_lifecycle", {}).get(sid_gov)
            if lc is not None:
                env = str(getattr(lc, "environment", "") or getattr(lc, "lifecycle", ""))
                lifecycle = env if env else "UNKNOWN"  # type: ignore[assignment]

        runtime = load_runtime_state(self._registry, code, default_lifecycle=lifecycle)
        if lifecycle != "UNKNOWN":
            runtime = runtime.model_copy(update={"lifecycle_phase": lifecycle})

        health, alerts = load_monitoring_context(self._monitoring, strategy_code=code)
        breaches = breaches_from_inject(section)
        if not breaches and alerts:
            breaches = breaches_from_alerts(alerts)
        if not breaches and health is not None:
            breaches = breaches_from_health_overall(
                strategy_code=code,
                overall=str(getattr(health, "overall", "")),
                dimensions=list(getattr(health, "dimensions", []) or []),
            )

        actions_applied: list[str] = []
        incidents: list[str] = []
        events: list[str] = []
        skipped: list[str] = []

        for breach in breaches:
            action = lookup_action(guard_policy.action_matrix, breach)
            if action is None:
                continue
            if action == "REVIEW":
                inc = open_incident(
                    strategy_code=code,
                    breach=breach,
                    recommended_action="REVIEW",
                    session_id=sid,
                    requires_decision=True,
                )
                inc = self._writer.write_incident(inc)
                incidents.append(inc.incident_id)
                runtime = runtime.model_copy(update={"last_incident_id": inc.incident_id})
                evt = self._emit_event(
                    code,
                    event_type="INCIDENT_OPENED",
                    runtime=runtime,
                    severity=breach.severity,
                    category=breach.category,
                    incident_id=inc.incident_id,
                    message=inc.message,
                    session_id=sid,
                )
                events.append(evt.event_id)
                continue

            can_auto = guard_policy.auto_execute and is_auto_allowed(auto_policy, action)
            if not can_auto:
                skipped.append(reject_auto_reason(action))
                inc = open_incident(
                    strategy_code=code,
                    breach=breach,
                    recommended_action=action,
                    session_id=sid,
                    requires_decision=True,
                )
                inc = self._writer.write_incident(
                    inc.model_copy(update={"status": "REVIEW_REQUIRED"})
                )
                incidents.append(inc.incident_id)
                continue

            assert_no_capital_reallocation(action=action)
            runtime = self._apply_auto_action(
                runtime,
                action=action,
                breach=breach,
                session_id=sid,
            )
            actions_applied.append(action)
            evt = self._emit_event(
                code,
                event_type=_event_type_for_action(action),  # type: ignore[arg-type]
                runtime=runtime,
                severity=breach.severity,
                category=breach.category,
                message=f"auto {action} for {breach.category}",
                session_id=sid,
            )
            events.append(evt.event_id)

        runtime = runtime.model_copy(
            update={
                "policy_id": guard_policy.policy_id,
                "policy_version": guard_policy.policy_version,
                "policy_content_hash": guard_policy.policy_content_hash,
                "last_evaluated_at": ts,
                "session_id": sid or runtime.session_id,
            }
        )
        runtime = self._writer.write_runtime(runtime)

        return GuardrailEvaluationResult(
            strategy_code=code,
            runtime=runtime,
            actions_applied=actions_applied,
            incidents=incidents,
            events=events,
            skipped_forbidden=skipped,
            evaluated_at=ts,
            session_id=sid,
        )

    def _apply_auto_action(
        self,
        runtime: StrategyRuntimeState,
        *,
        action: str,
        breach: Any,
        session_id: str,
    ) -> StrategyRuntimeState:
        sid = strategy_id_from_code(runtime.strategy_code)
        reason = f"guardrail:{breach.category}:{breach.severity}"
        if action == "WARN":
            return apply_warn(runtime, event=self._stub_event(runtime, session_id))
        if action == "THROTTLE":
            tier = "THROTTLED_50"
            if breach.metric == "slippage_bps":
                tier = "THROTTLED_50"
            return apply_throttle(
                runtime,
                tier=tier,  # type: ignore[arg-type]
                governance=self._governance,
                strategy_id=sid,
                reason=reason,
            )
        if action == "PAUSE":
            return apply_pause(
                runtime,
                governance=self._governance,
                strategy_id=sid,
                reason=reason,
            )
        if action == "SAFETY_STOP":
            return apply_safety_stop(
                runtime,
                safety=self._safety,
                strategy_id=sid,
                reason=reason,
            )
        return runtime

    def _stub_event(self, runtime: StrategyRuntimeState, session_id: str) -> GovernanceEvent:
        ts = _now()
        return GovernanceEvent(
            event_id=build_governance_event_id(
                strategy_code=runtime.strategy_code,
                event_type="STRATEGY_WARNED",
                created_at=ts,
            ),
            strategy_code=runtime.strategy_code,
            event_type="STRATEGY_WARNED",
            runtime_status=runtime.runtime_status,
            lifecycle_phase=runtime.lifecycle_phase,
            created_at=ts,
            session_id=session_id,
        )

    def _emit_event(
        self,
        strategy_code: str,
        *,
        event_type: str,
        runtime: StrategyRuntimeState,
        severity: str = "INFO",
        category: str = "SYSTEM",
        incident_id: str = "",
        decision_id: str = "",
        message: str = "",
        session_id: str = "",
    ) -> GovernanceEvent:
        ts = _now()
        evt = GovernanceEvent(
            event_id=build_governance_event_id(
                strategy_code=strategy_code,
                event_type=event_type,
                created_at=ts,
            ),
            strategy_code=strategy_code,
            event_type=event_type,  # type: ignore[arg-type]
            runtime_status=runtime.runtime_status,
            lifecycle_phase=runtime.lifecycle_phase,
            severity=severity,
            category=category,
            incident_id=incident_id,
            decision_id=decision_id,
            message=message,
            created_at=ts,
            session_id=session_id,
        )
        return self._writer.write_event(evt)

    def get_runtime_state(self, strategy_code: str) -> StrategyRuntimeState:
        code = str(strategy_code or "").strip()
        return load_runtime_state(self._registry, code)

    def list_incidents(self, strategy_code: str) -> list[GovernanceIncident]:
        rows = self._registry.list_governance_incidents(strategy_code=strategy_code)
        return [
            GovernanceIncident(
                incident_id=r.incident_id,
                strategy_code=r.strategy_code,
                status=r.status,  # type: ignore[arg-type]
                severity=r.severity,
                category=r.category,
                recommended_action=r.recommended_action,  # type: ignore[arg-type]
                alert_id=r.alert_id,
                message=r.message,
                requires_decision=bool(r.requires_decision),
                opened_at=r.opened_at or "",
                resolved_at=r.resolved_at or "",
                session_id=r.session_id or "",
                storage_uri=r.storage_uri or "",
                metadata=dict(r.metadata or {}),
            )
            for r in rows
        ]

    def get_incident(self, incident_id: str) -> GovernanceIncident:
        row = self._registry.get_governance_incident(incident_id)
        return GovernanceIncident(
            incident_id=row.incident_id,
            strategy_code=row.strategy_code,
            status=row.status,  # type: ignore[arg-type]
            severity=row.severity,
            category=row.category,
            recommended_action=row.recommended_action,  # type: ignore[arg-type]
            alert_id=row.alert_id,
            message=row.message,
            requires_decision=bool(row.requires_decision),
            opened_at=row.opened_at or "",
            resolved_at=row.resolved_at or "",
            session_id=row.session_id or "",
            storage_uri=row.storage_uri or "",
            metadata=dict(row.metadata or {}),
        )

    def submit_decision(self, decision: GovernanceDecision) -> GovernanceDecision:
        saved = self._writer.write_decision(decision)
        runtime = self.get_runtime_state(saved.strategy_code)
        evt = self._emit_event(
            saved.strategy_code,
            event_type="DECISION_SUBMITTED",
            runtime=runtime,
            decision_id=saved.decision_id,
            message=f"decision {saved.decision_type} {saved.status}",
            session_id=saved.session_id,
        )
        _ = evt
        return saved

    def execute_approved_decision(self, decision_id: str) -> GovernanceDecision:
        row = self._registry.get_governance_decision(decision_id)
        decision = GovernanceDecision(
            decision_id=row.decision_id,
            strategy_code=row.strategy_code,
            incident_id=row.incident_id,
            decision_type=row.decision_type,  # type: ignore[arg-type]
            status=row.status,  # type: ignore[arg-type]
            operator=row.operator,
            reason=row.reason,
            to_version=row.to_version,
            submitted_at=row.submitted_at or "",
            approved_at=row.approved_at or "",
            executed_at=row.executed_at or "",
            session_id=row.session_id or "",
        )
        assert_executable(decision)
        runtime = self.get_runtime_state(decision.strategy_code)
        dtype = str(decision.decision_type).upper()
        if dtype == "STOP":
            runtime = apply_safety_stop(
                runtime,
                safety=self._safety,
                strategy_id=strategy_id_from_code(decision.strategy_code),
                reason=decision.reason or "governance_stop",
            )
        elif dtype == "PAUSE":
            runtime = apply_pause(
                runtime,
                governance=self._governance,
                strategy_id=strategy_id_from_code(decision.strategy_code),
                reason=decision.reason,
            )
        elif dtype == "THROTTLE":
            runtime = apply_throttle(
                runtime,
                governance=self._governance,
                strategy_id=strategy_id_from_code(decision.strategy_code),
                reason=decision.reason,
            )
        elif dtype == "ROLLBACK":
            if not decision.to_version:
                raise GuardrailDecisionError("to_version required for rollback")
            runtime, rb = apply_rollback(
                runtime,
                to_version=decision.to_version,
                reason=decision.reason,
                operator=decision.operator,
                decision_id=decision.decision_id,
                promotion=self._promotion,
                governance=self._governance,
                session_id=decision.session_id,
            )
            self._writer.write_rollback(
                GuardrailRollbackRecord(
                    **rb.model_dump(),
                    from_model_version=rb.from_model_version,
                    to_model_version=rb.to_model_version,
                )
            )
        elif dtype == "RESUME":
            runtime = apply_resume(
                runtime,
                recovery_ok=runtime.recovery_check_passed,
                decision_approved=True,
            )
        elif dtype == "CONTINUE":
            pass
        else:
            raise GuardrailDecisionError(f"unsupported decision: {dtype}")

        runtime = self._writer.write_runtime(runtime)
        ts = _now()
        executed = decision.model_copy(update={"status": "EXECUTED", "executed_at": ts})
        executed = self._writer.write_decision(executed)
        self._emit_event(
            decision.strategy_code,
            event_type="DECISION_EXECUTED",
            runtime=runtime,
            decision_id=decision.decision_id,
            message=f"executed {dtype}",
            session_id=decision.session_id,
        )
        return executed

    def resume(
        self,
        strategy_code: str,
        *,
        operator: str = "",
        auto: bool = False,
        inject: Mapping[str, Any] | None = None,
    ) -> StrategyRuntimeState:
        code = str(strategy_code or "").strip()
        _, auto_policy = resolve_guardrail_policies(self._registry)
        section = merge_guardrail_inject(inject)
        recovery_override = recovery_healthy_from_inject(section)
        runtime = self.get_runtime_state(code)
        recovery_ok = runtime.recovery_check_passed
        if recovery_override is not None:
            recovery_ok = recovery_override
        elif auto and self._monitoring is not None:
            try:
                health = self._monitoring.get_health(code)
                recovery_ok = str(health.overall).upper() in ("HEALTHY", "WARNING")
            except Exception:
                recovery_ok = False
        try:
            runtime = apply_resume(
                runtime,
                recovery_ok=recovery_ok,
                auto_resume_allowed=auto_policy.auto_resume if auto else False,
                decision_approved=False,
            )
        except ResumeBlockedError as exc:
            raise StrategyGuardrailsError(str(exc)) from exc
        if not auto:
            dec = new_decision(
                strategy_code=code,
                decision_type="RESUME",
                operator=operator,
                status="PENDING",
            )
            dec = approve_decision(dec, operator=operator or "operator")
            self._writer.write_decision(dec)
        runtime = self._writer.write_runtime(runtime)
        self._emit_event(
            code,
            event_type="STRATEGY_RESUMED",
            runtime=runtime,
            message="resume",
        )
        return runtime

    def rollback(
        self,
        strategy_code: str,
        to_version: str,
        *,
        decision_id: str = "",
        operator: str = "",
        from_version: str = "",
    ) -> GuardrailRollbackRecord:
        runtime = self.get_runtime_state(strategy_code)
        runtime, record = apply_rollback(
            runtime,
            to_version=to_version,
            reason="manual rollback",
            operator=operator,
            decision_id=decision_id,
            promotion=self._promotion,
            governance=self._governance,
            from_version=from_version,
        )
        self._writer.write_runtime(runtime)
        return self._writer.write_rollback(record)

    def list_events(self, strategy_code: str) -> list[GovernanceEvent]:
        rows = self._registry.list_guardrail_governance_events(strategy_code=strategy_code)
        return [
            GovernanceEvent(
                event_id=r.event_id,
                strategy_code=r.strategy_code,
                event_type=r.event_type,  # type: ignore[arg-type]
                runtime_status=r.runtime_status,  # type: ignore[arg-type]
                lifecycle_phase=r.lifecycle_phase,  # type: ignore[arg-type]
                severity=r.severity,
                category=r.category,
                incident_id=r.incident_id,
                decision_id=r.decision_id,
                message=r.message,
                created_at=r.created_at or "",
                session_id=r.session_id or "",
                metadata=dict(r.metadata or {}),
            )
            for r in rows
        ]


__all__ = [
    "GuardrailDecisionError",
    "StrategyGuardrailsError",
    "StrategyGuardrailsService",
]
