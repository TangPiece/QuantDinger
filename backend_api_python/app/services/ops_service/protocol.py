"""Phase 6H：Monitoring / Audit / Alert 领域契约（不拥有订单与持仓）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from app.services.research_data.contracts import _ContractModel

ENGINE_VERSION = "qd_ops@1"

HealthStatus = Literal["HEALTHY", "DEGRADED", "UNHEALTHY"]
AlertSeverity = Literal["INFO", "WARNING", "ERROR", "CRITICAL"]
ActorType = Literal["SYSTEM", "STRATEGY", "OPERATOR", "BROKER", "SCHEDULER"]
IncidentStatus = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]


class ComponentHealth(_ContractModel):
    """单组件健康；含子组件时可嵌套 metadata。"""

    name: str
    status: HealthStatus = "HEALTHY"
    message: str = ""
    checked_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TradingHealth(_ContractModel):
    """交易链路聚合健康。"""

    overall: HealthStatus = "HEALTHY"
    broker: ComponentHealth = Field(default_factory=lambda: ComponentHealth(name="broker"))
    oms: ComponentHealth = Field(default_factory=lambda: ComponentHealth(name="oms"))
    safety: ComponentHealth = Field(default_factory=lambda: ComponentHealth(name="safety"))
    reconciliation: ComponentHealth = Field(
        default_factory=lambda: ComponentHealth(name="reconciliation")
    )
    market_data: ComponentHealth = Field(
        default_factory=lambda: ComponentHealth(name="market_data")
    )
    components: list[ComponentHealth] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditActor(_ContractModel):
    """审计操作主体。"""

    actor_type: ActorType = "SYSTEM"
    actor_id: str = ""


class AuditEvent(_ContractModel):
    """只追加审计事件；状态变更用新事件链接，禁止覆盖历史。"""

    event_id: str
    event_type: str
    timestamp: Optional[str] = None
    actor: AuditActor = Field(default_factory=AuditActor)
    trace_id: str = ""
    account_id: str = ""
    strategy_id: str = ""
    order_id: str = ""
    entity_type: str = ""
    entity_id: str = ""
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AlertRule(_ContractModel):
    """告警规则；阈值来自配置，不在代码硬编码 SLO 数字。"""

    rule_id: str
    enabled: bool = True
    metric_or_signal: str = ""
    severity: AlertSeverity = "WARNING"
    threshold: float = 0.0
    comparison: Literal["GT", "GTE", "LT", "LTE", "EQ"] = "GT"
    description: str = ""
    # 仅 CRITICAL 且列在此处的 rule 才映射 Safety report_source
    safety_source_kind: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AlertEvent(_ContractModel):
    """一次规则触发的告警实例。"""

    alert_id: str
    rule_id: str
    severity: AlertSeverity = "WARNING"
    fired_at: Optional[str] = None
    message: str = ""
    account_id: str = ""
    strategy_id: str = ""
    trace_id: str = ""
    incident_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class Incident(_ContractModel):
    """将 Alert / Audit / Safety / Recon 按 trace 或 account 聚合。"""

    incident_id: str
    title: str = ""
    severity: AlertSeverity = "WARNING"
    status: IncidentStatus = "OPEN"
    account_id: str = ""
    strategy_id: str = ""
    trace_id: str = ""
    opened_at: Optional[str] = None
    updated_at: Optional[str] = None
    resolved_at: Optional[str] = None
    timeline_event_ids: list[str] = Field(default_factory=list)
    alert_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SLODefinition(_ContractModel):
    """交易 SLO 定义（配置化，验收不依赖具体数值）。"""

    slo_id: str
    name: str = ""
    target_ratio: float = 0.999
    window_sec: float = 86400.0
    metric_name: str = ""
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class TradingOpsSnapshot(_ContractModel):
    """一次健康采集 + 低基数指标快照。"""

    snapshot_id: str
    captured_at: Optional[str] = None
    health: TradingHealth = Field(default_factory=TradingHealth)
    counters: dict[str, float] = Field(default_factory=dict)
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ENGINE_VERSION",
    "ActorType",
    "AlertEvent",
    "AlertRule",
    "AlertSeverity",
    "AuditActor",
    "AuditEvent",
    "ComponentHealth",
    "HealthStatus",
    "Incident",
    "IncidentStatus",
    "SLODefinition",
    "TradingHealth",
    "TradingOpsSnapshot",
]
