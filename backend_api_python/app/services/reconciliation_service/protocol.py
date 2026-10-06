"""Phase 6F：Reconciliation Domain（观察者；禁止直接改 OMS/持仓）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from app.services.broker_adapter.protocol import (
    BrokerAccountView,
    BrokerOrderView,
    BrokerPositionView,
)
from app.services.research_data.contracts import _ContractModel

ENGINE_VERSION = "qd_reconciliation@1"

RunMode = Literal["FAST", "SLOW", "EOD"]
FindingSeverity = Literal["INFO", "WARNING", "ERROR", "CRITICAL"]
FindingStatus = Literal[
    "OPEN", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "WAIVED"
]
FindingType = Literal[
    "ORDER_MISMATCH",
    "FILL_MISMATCH",
    "POSITION_MISMATCH",
    "CASH_MISMATCH",
    "PNL_MISMATCH",
    "UNEXPECTED_ORDER",
    "UNEXPECTED_FILL",
    "MISSING_ORDER",
    "MISSING_FILL",
]
CursorType = Literal["EXECUTION", "ORDER", "SNAPSHOT_TIME"]
EntityType = Literal["ORDER", "FILL", "POSITION", "CASH", "PNL", "ACCOUNT"]


class BrokerExecutionView(_ContractModel):
    """Snapshot 内标准化成交行（禁止 compare 层解析券商原始 JSON）。"""

    broker_execution_id: str
    client_order_id: str = ""
    order_id: str = ""
    quantity: float = 0.0
    price: float = 0.0
    fee: float = 0.0
    ts: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrokerSnapshot(_ContractModel):
    """Adapter.get_* 归一化结果；compare 唯一外部输入。"""

    snapshot_id: str
    broker_id: str = ""
    account_id: str = ""
    captured_at: str = ""
    account: BrokerAccountView = Field(default_factory=BrokerAccountView)
    positions: list[BrokerPositionView] = Field(default_factory=list)
    open_orders: list[BrokerOrderView] = Field(default_factory=list)
    executions: list[BrokerExecutionView] = Field(default_factory=list)
    raw_storage_uri: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReconciliationFinding(_ContractModel):
    """对账差异；CRITICAL 不可 Waive。"""

    finding_id: str
    run_id: str = ""
    type: FindingType
    severity: FindingSeverity = "WARNING"
    status: FindingStatus = "OPEN"
    entity_type: EntityType = "ORDER"
    entity_id: str = ""
    expected: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any] = Field(default_factory=dict)
    difference: dict[str, Any] = Field(default_factory=dict)
    detected_at: Optional[str] = None
    resolved_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReconciliationRun(_ContractModel):
    """一次 Fast/Slow/EOD 对账运行摘要。"""

    run_id: str
    account_id: str = ""
    portfolio_id: str = ""
    broker_id: str = ""
    mode: RunMode = "FAST"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    snapshot_id: str = ""
    finding_count: int = 0
    critical_count: int = 0
    info_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    gate_blocked: bool = False
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class GateState(_ContractModel):
    """Trading Gate：CRITICAL OPEN → 阻断新 submit。"""

    account_id: str
    blocked: bool = False
    reason: str = ""
    finding_id: str = ""
    updated_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReconciliationCursor(_ContractModel):
    """增量游标：EXECUTION / ORDER / SNAPSHOT_TIME。"""

    account_id: str
    broker_id: str = ""
    cursor_type: CursorType
    cursor_value: str = ""
    updated_at: Optional[str] = None


__all__ = [
    "ENGINE_VERSION",
    "BrokerExecutionView",
    "BrokerSnapshot",
    "CursorType",
    "EntityType",
    "FindingSeverity",
    "FindingStatus",
    "FindingType",
    "GateState",
    "ReconciliationCursor",
    "ReconciliationFinding",
    "ReconciliationRun",
    "RunMode",
]
