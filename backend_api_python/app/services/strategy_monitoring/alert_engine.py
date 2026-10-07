"""Phase 8F：AlertEngine — evaluate / dedupe / cooldown / escalate。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .identity import build_alert_fingerprint, build_alert_id
from .protocol import (
    AlertRule,
    AlertSeverity,
    AlertStatus,
    MonitoringMetric,
    MonitorPolicyRecord,
    StrategyAlert,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(text: str) -> datetime | None:
    t = str(text or "").strip()
    if not t:
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None


def _compare(value: float, threshold: float, op: str) -> bool:
    if op == "gt":
        return value > threshold
    if op == "gte":
        return value >= threshold
    if op == "lt":
        return value < threshold
    if op == "lte":
        return value <= threshold
    return value > threshold


def _severity_for_rule(rule: AlertRule, value: float) -> AlertSeverity | None:
    if not rule.enabled:
        return None
    if _compare(value, rule.critical_threshold, rule.compare):
        return "CRITICAL"
    if _compare(value, rule.warning_threshold, rule.compare):
        return "WARNING"
    return None


def _metric_value(metrics: list[MonitoringMetric], rule: AlertRule) -> float | None:
    for m in metrics:
        if m.category == rule.category and m.name == rule.metric:
            return float(m.value)
    return None


def evaluate_rules(
    *,
    strategy_code: str,
    policy: MonitorPolicyRecord,
    metrics: list[MonitoringMetric],
    now: datetime | None = None,
    session_id: str = "",
) -> list[tuple[AlertRule, AlertSeverity, float, str]]:
    """返回 (rule, severity, value, fingerprint) 待触发列表。"""
    ts = now or _now()
    _ = ts
    out: list[tuple[AlertRule, AlertSeverity, float, str]] = []
    for rule in policy.rules:
        val = _metric_value(metrics, rule)
        if val is None:
            continue
        sev = _severity_for_rule(rule, val)
        if sev is None:
            continue
        fp = build_alert_fingerprint(
            rule_id=rule.rule_id,
            category=rule.category,
            metric=rule.metric,
            value=val,
        )
        out.append((rule, sev, val, fp))
    return out


def merge_alert(
    *,
    strategy_code: str,
    rule: AlertRule,
    severity: AlertSeverity,
    value: float,
    fingerprint: str,
    existing: StrategyAlert | None,
    now: datetime | None = None,
    session_id: str = "",
) -> tuple[StrategyAlert, bool]:
    """合并 dedupe；返回 (alert, should_notify)。"""
    ts = now or _now()
    now_s = _iso(ts)
    aid = build_alert_id(
        strategy_code=strategy_code, rule_id=rule.rule_id, fingerprint=fingerprint
    )
    title = f"{rule.category}/{rule.metric}"
    message = f"{rule.description or rule.metric}={value} ({severity})"

    if existing is None:
        alert = StrategyAlert(
            alert_id=aid,
            strategy_code=strategy_code,
            rule_id=rule.rule_id,
            fingerprint=fingerprint,
            category=rule.category,
            severity=severity,
            status="OPEN",
            title=title,
            message=message,
            occurrence_count=1,
            consecutive_critical_count=1 if severity == "CRITICAL" else 0,
            first_seen_at=now_s,
            last_seen_at=now_s,
            cooldown_until=_iso(ts + timedelta(seconds=rule.cooldown_seconds)),
            suppressed_until=_iso(ts + timedelta(seconds=rule.suppression_seconds)),
            session_id=session_id,
        )
        if (
            alert.consecutive_critical_count >= rule.consecutive_for_emergency
            and alert.severity == "CRITICAL"
        ):
            alert = alert.model_copy(update={"severity": "EMERGENCY"})
        return alert, True

    status: AlertStatus = existing.status
    if status == "RESOLVED":
        status = "REOPENED"

    occ = existing.occurrence_count + 1
    consec = existing.consecutive_critical_count
    if severity == "CRITICAL":
        consec += 1
    else:
        consec = 0

    sev: AlertSeverity = severity
    if consec >= rule.consecutive_for_emergency and severity == "CRITICAL":
        sev = "EMERGENCY"

    cooldown_until = existing.cooldown_until
    cd = _parse_iso(cooldown_until)
    should_notify = False
    if cd is None or ts >= cd:
        should_notify = True
        cooldown_until = _iso(ts + timedelta(seconds=rule.cooldown_seconds))

    alert = existing.model_copy(
        update={
            "severity": sev,
            "status": status,
            "message": message,
            "occurrence_count": occ,
            "consecutive_critical_count": consec,
            "last_seen_at": now_s,
            "cooldown_until": cooldown_until,
            "session_id": session_id or existing.session_id,
        }
    )
    return alert, should_notify


__all__ = ["evaluate_rules", "merge_alert"]
