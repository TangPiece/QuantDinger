"""Phase 6J：生产就绪验收契约（Hardening，不扩交易能力）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from app.services.oms.protocol import RecoverReport
from app.services.research_data.contracts import _ContractModel

ENGINE_VERSION = "qd_readiness@1"

CheckStatus = Literal["OK", "FAILED", "SKIPPED"]


class ReadinessCheck(_ContractModel):
    """单项就绪检查。"""

    check_id: str
    title: str = ""
    status: CheckStatus = "OK"
    scenario_id: str = ""
    messages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChecklistResult(_ContractModel):
    """PRODUCTION_READY 聚合结果。"""

    run_id: str
    production_ready: bool = False
    checks: list[ReadinessCheck] = Field(default_factory=list)
    recover_report: Optional[RecoverReport] = None
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class FaultCase(_ContractModel):
    """故障注入用例（catalog）。"""

    fault_id: str
    title: str = ""
    category: str = ""
    expected_behavior: str = ""
    recovery_procedure: str = ""
    runnable: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class FaultResult(_ContractModel):
    """故障注入执行结果。"""

    fault_id: str
    status: CheckStatus = "OK"
    expected_behavior: str = ""
    actual_behavior: str = ""
    messages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TradingSLO(_ContractModel):
    """交易 SLO 定义（数值可调，验收时不硬编码达标）。"""

    slo_id: str
    name: str = ""
    target_ratio: float = 1.0
    window_sec: float = 86400.0
    metric_name: str = ""
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenarioSpec(_ContractModel):
    """RDY 场景规格（与 6I 同构，独立 harness）。"""

    scenario_id: str
    title: str = ""
    fixture_id: str = ""
    instrument_key: str = ""
    target_quantity: float = 0.0
    side: Literal["BUY", "SELL"] = "BUY"
    execution_algorithm: Literal["MARKET", "LIMIT"] = "MARKET"
    limit_price: Optional[float] = None
    broker_inject: dict[str, Any] = Field(default_factory=dict)
    risk_policy_overrides: dict[str, Any] = Field(default_factory=dict)
    pre_actions: list[str] = Field(default_factory=list)
    post_actions: list[str] = Field(default_factory=list)
    expect: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenarioResult(_ContractModel):
    """单次 RDY 场景结果。"""

    scenario_run_id: str
    scenario_id: str
    run_id: str = ""
    status: CheckStatus = "OK"
    order_ids: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ENGINE_VERSION",
    "CheckStatus",
    "ChecklistResult",
    "FaultCase",
    "FaultResult",
    "ReadinessCheck",
    "RecoverReport",
    "ScenarioResult",
    "ScenarioSpec",
    "TradingSLO",
]
