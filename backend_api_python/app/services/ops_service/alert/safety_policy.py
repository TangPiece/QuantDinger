"""CRITICAL 告警 → Safety report_source；WARNING 不触发 HALT。"""

from __future__ import annotations

from typing import Any

from ..protocol import AlertEvent, AlertRule

# 仅这两类 CRITICAL 映射 Safety（可经 AlertRule.safety_source_kind 覆盖）
_DEFAULT_CRITICAL_SOURCES = {
    "RECON_CRITICAL": "RECONCILIATION_CRITICAL",
    "UNEXPECTED_FILL": "UNEXPECTED_FILL",
}


def default_alert_rules() -> list[AlertRule]:
    """内置规则骨架；阈值来自 rule 配置而非硬编码 SLO。"""
    return [
        AlertRule(
            rule_id="BROKER_LATENCY",
            metric_or_signal="broker_response_latency_ms",
            severity="WARNING",
            threshold=500.0,
            comparison="GT",
            description="Broker latency elevated",
        ),
        AlertRule(
            rule_id="RECON_CRITICAL",
            metric_or_signal="reconciliation_critical",
            severity="CRITICAL",
            threshold=1.0,
            comparison="GTE",
            safety_source_kind="RECONCILIATION_CRITICAL",
            description="Reconciliation critical mismatch",
        ),
        AlertRule(
            rule_id="UNEXPECTED_FILL",
            metric_or_signal="unexpected_fill",
            severity="CRITICAL",
            threshold=1.0,
            comparison="GTE",
            safety_source_kind="UNEXPECTED_FILL",
            description="Unexpected fill detected",
        ),
    ]


def apply_safety_policy(
    alert: AlertEvent,
    *,
    rule: AlertRule | None,
    safety_service: Any = None,
    account_id: str = "",
) -> bool:
    """返回是否已上报 Safety；仅 CRITICAL + 已配置 source kind。"""
    if str(alert.severity).upper() != "CRITICAL":
        return False
    if safety_service is None:
        return False
    kind = ""
    if rule is not None:
        kind = str(rule.safety_source_kind or "").strip()
    if not kind:
        kind = _DEFAULT_CRITICAL_SOURCES.get(alert.rule_id, "")
    if not kind:
        return False
    acct = account_id or alert.account_id
    try:
        safety_service.report_source(
            kind,
            "ACCOUNT",
            acct,
            severity="CRITICAL",
            payload=dict(alert.metadata or {}),
        )
        return True
    except Exception:
        return False
