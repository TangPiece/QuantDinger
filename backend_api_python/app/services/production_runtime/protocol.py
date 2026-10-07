"""Phase 6A：Production Runtime Domain（停在 OrderIntent；无 Broker）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import Field

from app.services.research_data.contracts import (
    OrderIntent,
    ProductionRuntimeEventRecord,
    ProductionRuntimeRunSummary,
    ProductionRuntimeSummary,
    Signal,
    TargetPosition,
    _ContractModel,
)
from app.services.research_data.production_bridge.protocol import GateResult

ENGINE_VERSION = "qd_production_runtime@1"

RuntimeEnvironment = Literal["PAPER", "SHADOW", "LIVE_CONTROLLED"]
RuntimeMarket = Literal["CN_A", "HK", "US"]
RuntimeStatus = Literal[
    "STARTING",
    "READY",
    "RUNNING",
    "PAUSED",
    "DEGRADED",
    "STOPPING",
    "STOPPED",
    "ERROR",
]
SessionPhase = Literal[
    "PRE_MARKET",
    "MARKET_OPEN",
    "INTRADAY",
    "PRE_CLOSE",
    "MARKET_CLOSE",
    "POST_MARKET",
]

EventType = Literal[
    "BUNDLE_LOADED",
    "DATA_READY",
    "FEATURE_COMPUTED",
    "MODEL_INFERRED",
    "SIGNAL_GENERATED",
    "RISK_PASSED",
    "RISK_REJECTED",
    "ORDER_INTENT_CREATED",
    "SESSION_PHASE",
    "DATA_STALE",
    "RUNTIME_PAUSED",
    "RUNTIME_ERROR",
]


class RuntimeInstance(_ContractModel):
    """运行中实例（与 Summary 对齐的内存视图）。"""

    runtime_id: str
    bundle_hash: str
    strategy_code: str = ""
    market: RuntimeMarket = "CN_A"
    environment: RuntimeEnvironment = "PAPER"
    status: RuntimeStatus = "STARTING"
    session_phase: SessionPhase = "PRE_MARKET"
    trading_date: str = ""
    started_at: Optional[str] = None
    last_heartbeat: Optional[str] = None
    engine_version: str = ENGINE_VERSION
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TradingSession(_ContractModel):
    """交易日会话快照。"""

    market: RuntimeMarket = "CN_A"
    trading_date: date
    phase: SessionPhase = "PRE_MARKET"
    as_of: Optional[datetime] = None


class RuntimeTickResult(_ContractModel):
    """单次 tick 结果；不发单。"""

    runtime_id: str
    run_id: str
    idempotency_key: str
    trading_date: str
    session_phase: str
    status: Literal["OK", "STOPPED", "FAILED", "SKIPPED_IDEMPOTENT"] = "OK"
    reused: bool = False
    signals: list[Signal] = Field(default_factory=list)
    targets: list[TargetPosition] = Field(default_factory=list)
    order_intents: list[OrderIntent] = Field(default_factory=list)
    gate_results: list[GateResult] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    bridge_run_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeManifest(_ContractModel):
    runtime_id: str
    bundle_hash: str = ""
    engine_version: str = ENGINE_VERSION
    checksum: str = ""
    storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ENGINE_VERSION",
    "EventType",
    "GateResult",
    "ProductionRuntimeEventRecord",
    "ProductionRuntimeRunSummary",
    "ProductionRuntimeSummary",
    "RuntimeEnvironment",
    "RuntimeInstance",
    "RuntimeManifest",
    "RuntimeMarket",
    "RuntimeStatus",
    "RuntimeTickResult",
    "SessionPhase",
    "TradingSession",
]
