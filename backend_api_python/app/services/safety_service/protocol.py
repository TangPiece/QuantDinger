"""Phase 6G：Safety Domain（Kill Switch / Trading Gate；不拥有订单）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from app.services.research_data.contracts import _ContractModel

ENGINE_VERSION = "qd_safety@1"

GateDecisionKind = Literal["ALLOW", "BLOCK_NEW_ORDER", "HALT", "EMERGENCY"]
SafetyScope = Literal["STRATEGY", "ACCOUNT", "GLOBAL"]
SafetyStateName = Literal[
    "NORMAL", "DEGRADED", "HALTED", "EMERGENCY", "UNKNOWN"
]
SafetyActionIntent = Literal["CANCEL_OPEN_ORDERS", "FLATTEN_ALL"]
SafetyRuleId = Literal[
    "DAILY_LOSS_LIMIT",
    "MAX_DRAWDOWN",
    "POSITION_LIMIT",
    "ORDER_NOTIONAL_LIMIT",
    "ORDER_RATE_LIMIT",
    "RECONCILIATION_CRITICAL",
    "BROKER_DISCONNECT",
    "MARKET_DATA_STALE",
    "STRATEGY_ERROR",
    "SYSTEM_HEALTH",
    "KILL_SWITCH",
    "FAIL_CLOSED",
]
SourceKind = Literal[
    "RECONCILIATION_CRITICAL",
    "BROKER_DISCONNECT",
    "MARKET_DATA_STALE",
    "STRATEGY_ERROR",
    "SYSTEM_HEALTH",
    "MANUAL",
]


# 系统硬上限：可配置阈值不得松于这些值
class HardLimits(_ContractModel):
    """代码级硬上限；配置写入时校验。"""

    max_order_notional: float = 10_000_000.0
    max_orders_per_second: float = 50.0
    max_orders_per_minute: float = 500.0
    max_daily_loss_pct: float = -0.20  # 可配置不得低于 -20%（更负）
    max_drawdown_pct: float = 0.50
    max_position_qty: float = 1_000_000.0
    max_market_data_staleness_sec: float = 300.0


DEFAULT_HARD_LIMITS = HardLimits()


class TradingGateDecision(_ContractModel):
    """OMS submit 前最终决策。"""

    decision: GateDecisionKind = "ALLOW"
    scope: SafetyScope = "ACCOUNT"
    scope_id: str = ""
    rule_ids: list[str] = Field(default_factory=list)
    reason: str = ""
    fail_closed: bool = False
    actions: list[SafetyActionIntent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyState(_ContractModel):
    """按 scope 持久化的安全状态（热路径禁止走 R2）。"""

    scope: SafetyScope
    scope_id: str
    state: SafetyStateName = "NORMAL"
    acknowledged: bool = False
    reason: str = ""
    updated_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KillSwitch(_ContractModel):
    """三层 Kill Switch。"""

    scope: SafetyScope
    scope_id: str
    engaged: bool = False
    reason: str = ""
    engaged_at: Optional[str] = None
    engaged_by: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyRule(_ContractModel):
    """可配置规则；不得突破 HardLimits。"""

    rule_id: str
    enabled: bool = True
    threshold: float = 0.0
    action: GateDecisionKind = "BLOCK_NEW_ORDER"
    scope: SafetyScope = "ACCOUNT"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyEvent(_ContractModel):
    """安全审计事件（幂等 event_id）。"""

    event_id: str
    scope: SafetyScope = "ACCOUNT"
    scope_id: str = ""
    rule: str = ""
    severity: str = "WARNING"
    state_before: str = "NORMAL"
    state_after: str = "HALTED"
    reason: str = ""
    trigger_value: float = 0.0
    threshold: float = 0.0
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None
    operator: str = ""
    acknowledged: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmergencyStopIntent(_ContractModel):
    """紧急停止意图：P0 不自动 FLATTEN。"""

    intent_id: str
    scope: SafetyScope = "ACCOUNT"
    scope_id: str = ""
    stop_new_orders: bool = True
    cancel_open_orders: bool = False
    flatten_all: bool = False  # Contract only；P0 禁止自动执行
    reason: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyContext(_ContractModel):
    """单次 evaluate 输入快照（全部可注入，便于故障注入）。"""

    account_id: str = ""
    strategy_id: str = ""
    portfolio_id: str = ""
    instrument_key: str = ""
    side: str = "BUY"
    quantity: float = 0.0
    price: float = 0.0
    notional: float = 0.0
    # 限额输入
    current_position_qty: float = 0.0
    open_order_qty: float = 0.0
    pending_order_qty: float = 0.0
    net_daily_pnl_pct: float = 0.0
    drawdown_pct: float = 0.0
    peak_equity: float = 0.0
    current_equity: float = 0.0
    # 源状态
    recon_critical: bool = False
    broker_connected: bool = True
    market_data_age_sec: float = 0.0
    strategy_error_count: int = 0
    system_healthy: bool = True
    safety_state_known: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ENGINE_VERSION",
    "DEFAULT_HARD_LIMITS",
    "EmergencyStopIntent",
    "GateDecisionKind",
    "HardLimits",
    "KillSwitch",
    "SafetyActionIntent",
    "SafetyContext",
    "SafetyEvent",
    "SafetyRule",
    "SafetyRuleId",
    "SafetyScope",
    "SafetyState",
    "SafetyStateName",
    "SourceKind",
    "TradingGateDecision",
]
