"""健康采集 / 告警评估 / 审计辅助周期。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .alert.evaluate import evaluate_rules
from .alert.safety_policy import apply_safety_policy
from .audit.emit import emit_audit
from .hash import derive_health_snapshot_id
from .health.collectors import collect_all
from .health.aggregate import build_trading_health
from .incident.timeline import append_to_incident, open_incident
from .metrics.counters import increment_counter
from .protocol import AlertRule, AuditActor, TradingOpsSnapshot


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_collect_health(
    *,
    writer: Any,
    metrics: Any,
    account_id: str = "",
    broker_port: Any = None,
    safety_service: Any = None,
    recon_critical: bool = False,
    inject: Mapping[str, Any] | None = None,
    salt: str = "",
) -> TradingOpsSnapshot:
    """采集组件健康并持久化 snapshot。"""
    components = collect_all(
        broker_port=broker_port,
        safety_service=safety_service,
        account_id=account_id,
        recon_critical=recon_critical,
        inject=inject,
    )
    health = build_trading_health(components)
    sid = derive_health_snapshot_id(account_id=account_id or "global", salt=salt or _now())
    snap = TradingOpsSnapshot(
        snapshot_id=sid,
        captured_at=_now(),
        health=health,
        counters=metrics.snapshot() if metrics is not None else {},
        metadata={"account_id": account_id},
    )
    writer.write_health_snapshot(snap)
    return snap


def run_evaluate_alerts(
    *,
    writer: Any,
    rules: list[AlertRule],
    signals: Mapping[str, float],
    safety_service: Any = None,
    account_id: str = "",
    strategy_id: str = "",
    trace_id: str = "",
) -> list:
    """规则 → AlertEvent → Incident → 可选 Safety Policy。"""
    alerts = evaluate_rules(
        rules,
        signals,
        account_id=account_id,
        strategy_id=strategy_id,
        trace_id=trace_id,
    )
    out = []
    rule_by_id = {r.rule_id: r for r in rules}
    for alert in alerts:
        inc = open_incident(alert=alert, account_id=account_id, trace_id=trace_id)
        writer.write_incident(inc)
        alert = alert.model_copy(update={"incident_id": inc.incident_id})
        writer.write_alert_event(alert)
        apply_safety_policy(
            alert,
            rule=rule_by_id.get(alert.rule_id),
            safety_service=safety_service,
            account_id=account_id,
        )
        out.append(alert)
    return out


def audit_config_change(
    writer: Any,
    *,
    actor: AuditActor,
    entity_type: str,
    entity_id: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    reason: str = "",
    account_id: str = "",
) -> Any:
    """配置变更 before/after 审计。"""
    return emit_audit(
        writer,
        event_type="CONFIG_CHANGE",
        actor=actor,
        entity_type=entity_type,
        entity_id=entity_id,
        before=dict(before),
        after=dict(after),
        reason=reason,
        account_id=account_id,
        salt=f"{entity_type}|{entity_id}",
    )


def record_order_metric(
    metrics: Any,
    name: str,
    *,
    broker: str = "",
    account: str = "",
    strategy: str = "",
) -> None:
    """订单相关 counter；禁止 symbol label。"""
    increment_counter(
        metrics,
        name,
        labels={"broker": broker, "account": account, "strategy": strategy},
    )


def on_broker_disconnect(
    writer: Any,
    *,
    account_id: str = "",
    broker_id: str = "",
) -> Any:
    """Broker 断开：HEALTH 审计事件。"""
    return emit_audit(
        writer,
        event_type="HEALTH_BROKER_DISCONNECT",
        actor=AuditActor(actor_type="BROKER", actor_id=broker_id),
        account_id=account_id,
        reason="broker disconnected",
        salt=broker_id,
    )


def on_broker_recovery(
    writer: Any,
    *,
    account_id: str = "",
    broker_id: str = "",
) -> Any:
    """Broker 恢复连接审计。"""
    return emit_audit(
        writer,
        event_type="HEALTH_BROKER_RECOVERY",
        actor=AuditActor(actor_type="BROKER", actor_id=broker_id),
        account_id=account_id,
        reason="broker reconnected",
        salt=broker_id,
    )
