"""Phase 8F：内置 MonitorPolicy preset（default_monitor_v1）。"""

from __future__ import annotations

from .pin import policy_content_hash
from .protocol import AlertRule, MarketDataPolicy, MonitorPolicyRecord

DEFAULT_MONITOR_POLICY_ID = "default_monitor_v1"
DEFAULT_POLICY_VERSION = "v1"


def _default_rules() -> list[AlertRule]:
    return [
        AlertRule(
            rule_id="perf_shadow_drift",
            category="PERFORMANCE",
            metric="shadow_drift",
            description="8E shadow 漂移",
            warning_threshold=0.08,
            critical_threshold=0.15,
            compare="gt",
        ),
        AlertRule(
            rule_id="perf_drawdown",
            category="PERFORMANCE",
            metric="max_drawdown",
            description="回撤恶化",
            warning_threshold=0.12,
            critical_threshold=0.20,
            compare="gt",
        ),
        AlertRule(
            rule_id="risk_gross_util",
            category="RISK",
            metric="gross_exposure_util",
            description="总敞口利用率",
            warning_threshold=0.85,
            critical_threshold=1.0,
            compare="gte",
        ),
        AlertRule(
            rule_id="risk_turnover_util",
            category="RISK",
            metric="turnover_util",
            description="换手利用率",
            warning_threshold=0.90,
            critical_threshold=1.05,
            compare="gte",
        ),
        AlertRule(
            rule_id="market_data_staleness",
            category="MARKET_DATA",
            metric="staleness_seconds",
            description="行情延迟",
            warning_threshold=120.0,
            critical_threshold=300.0,
            compare="gt",
        ),
        AlertRule(
            rule_id="recon_open_findings",
            category="RECONCILIATION",
            metric="critical_finding_count",
            description="对账 CRITICAL finding",
            warning_threshold=0.5,
            critical_threshold=1.0,
            compare="gte",
        ),
        AlertRule(
            rule_id="exec_reject_rate",
            category="EXECUTION",
            metric="reject_rate",
            description="拒单率",
            warning_threshold=0.08,
            critical_threshold=0.15,
            compare="gt",
        ),
        AlertRule(
            rule_id="signal_correlation",
            category="SIGNAL",
            metric="signal_correlation",
            description="信号相关性下降",
            warning_threshold=0.85,
            critical_threshold=0.70,
            compare="lt",
        ),
    ]


def default_monitor_v1() -> MonitorPolicyRecord:
    pid = DEFAULT_MONITOR_POLICY_ID
    pver = DEFAULT_POLICY_VERSION
    rules = _default_rules()
    md = MarketDataPolicy()
    return MonitorPolicyRecord(
        policy_id=pid,
        policy_version=pver,
        policy_content_hash=policy_content_hash(
            policy_id=pid, policy_version=pver, rules=rules, market_data=md
        ),
        rules=rules,
        market_data=md,
        description="默认策略监控规则（仅 ALERT / REVIEW）",
    )


def get_default_preset() -> MonitorPolicyRecord:
    return default_monitor_v1().model_copy(deep=True)


__all__ = [
    "DEFAULT_MONITOR_POLICY_ID",
    "DEFAULT_POLICY_VERSION",
    "default_monitor_v1",
    "get_default_preset",
]
