"""Phase 8F：Strategy Monitoring 契约（只观察，不自动降级 / 不改 Version）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_strategy_monitoring@1"

HealthStatus = Literal[
    "UNKNOWN",
    "HEALTHY",
    "WARNING",
    "DEGRADED",
    "CRITICAL",
    "HALTED",
]
AlertSeverity = Literal["INFO", "WARNING", "CRITICAL", "EMERGENCY"]
AlertStatus = Literal[
    "OPEN",
    "ACKNOWLEDGED",
    "INVESTIGATING",
    "RESOLVED",
    "REOPENED",
]
MetricCategory = Literal[
    "PERFORMANCE",
    "RISK",
    "SIGNAL",
    "PORTFOLIO",
    "EXECUTION",
    "MARKET_DATA",
    "RECONCILIATION",
    "CAPACITY",
    "SYSTEM",
    "DATA_QUALITY",
]
GovernanceEventType = Literal["REVIEW_REQUIRED"]
NotificationChannel = Literal[
    "RECORDING",
    "FAKE",
    "EMAIL",
    "TELEGRAM",
    "SLACK",
    "WEBHOOK",
]


class _MonModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MonitoringMetric(_MonModel):
    """单条监控指标（带分类与健康态）。"""

    metric_id: str
    strategy_code: str
    category: MetricCategory
    name: str
    value: float = 0.0
    unit: str = ""
    health: HealthStatus = "UNKNOWN"
    window: str = "5m"
    collected_at: str = ""
    session_id: str = ""
    labels: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class DimensionHealth(_MonModel):
    category: MetricCategory
    status: HealthStatus = "UNKNOWN"
    summary: str = ""
    metric_count: int = 0


class StrategyHealth(_MonModel):
    """策略级健康快照（维度 + overall）。"""

    snapshot_id: str
    strategy_code: str
    overall: HealthStatus = "UNKNOWN"
    dimensions: list[DimensionHealth] = Field(default_factory=list)
    policy_id: str = ""
    policy_version: str = ""
    policy_content_hash: str = ""
    evaluated_at: str = ""
    session_id: str = ""
    engine_version: str = ENGINE_VERSION
    storage_uri: str = ""


class AlertRule(_MonModel):
    """单条告警规则（仅触发 Alert，不改环境）。"""

    rule_id: str
    category: MetricCategory
    metric: str
    description: str = ""
    warning_threshold: float = 0.0
    critical_threshold: float = 0.0
    compare: Literal["gt", "gte", "lt", "lte"] = "gt"
    cooldown_seconds: int = 300
    suppression_seconds: int = 60
    consecutive_for_emergency: int = 3
    enabled: bool = True


class MarketDataPolicy(_MonModel):
    """行情新鲜度策略片段。"""

    max_staleness_seconds: float = 120.0
    critical_staleness_seconds: float = 300.0


class MonitorPolicyRecord(_MonModel):
    """MonitorPolicy SSOT（版本化 + content_hash）。"""

    policy_id: str
    policy_version: str
    policy_content_hash: str
    rules: list[AlertRule] = Field(default_factory=list)
    market_data: MarketDataPolicy = Field(default_factory=MarketDataPolicy)
    engine_version: str = ENGINE_VERSION
    description: str = ""


class StrategyAlert(_MonModel):
    """告警实体（dedupe + lifecycle）。"""

    alert_id: str
    strategy_code: str
    rule_id: str
    fingerprint: str
    category: MetricCategory
    severity: AlertSeverity
    status: AlertStatus = "OPEN"
    title: str = ""
    message: str = ""
    occurrence_count: int = 1
    consecutive_critical_count: int = 0
    first_seen_at: str = ""
    last_seen_at: str = ""
    cooldown_until: str = ""
    suppressed_until: str = ""
    acknowledged_at: str = ""
    investigating_at: str = ""
    resolved_at: str = ""
    session_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotificationDispatch(_MonModel):
    """通知派发记录（Recording/Fake，不真发外部）。"""

    dispatch_id: str
    strategy_code: str
    alert_id: str
    channel: NotificationChannel = "RECORDING"
    severity: AlertSeverity = "INFO"
    payload_json: dict[str, Any] = Field(default_factory=dict)
    dispatched_at: str = ""
    session_id: str = ""


class GovernanceReviewEvent(_MonModel):
    """治理复核事件（REVIEW_REQUIRED，不改策略）。"""

    event_id: str
    strategy_code: str
    event_type: GovernanceEventType = "REVIEW_REQUIRED"
    severity: AlertSeverity = "CRITICAL"
    category: MetricCategory = "SYSTEM"
    alert_id: str = ""
    message: str = ""
    created_at: str = ""
    session_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DashboardSnapshot(_MonModel):
    """Dashboard 查询聚合（只读）。"""

    strategy_code: str
    health: StrategyHealth
    active_alerts: list[StrategyAlert] = Field(default_factory=list)
    recent_metrics: list[MonitoringMetric] = Field(default_factory=list)
    performance: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    execution: dict[str, Any] = Field(default_factory=dict)
    drift: dict[str, Any] = Field(default_factory=dict)
    reconciliation: dict[str, Any] = Field(default_factory=dict)
    generated_at: str = ""


__all__ = [
    "ENGINE_VERSION",
    "AlertRule",
    "AlertSeverity",
    "AlertStatus",
    "DashboardSnapshot",
    "DimensionHealth",
    "GovernanceEventType",
    "GovernanceReviewEvent",
    "HealthStatus",
    "MarketDataPolicy",
    "MetricCategory",
    "MonitorPolicyRecord",
    "MonitoringMetric",
    "NotificationChannel",
    "NotificationDispatch",
    "StrategyAlert",
    "StrategyHealth",
]
