"""Phase 6I：Paper / Shadow E2E 领域契约（编排层，不拥有订单）。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from app.services.research_data.contracts import TargetPosition, _ContractModel

ENGINE_VERSION = "qd_e2e@1"

E2EMode = Literal["PAPER", "SHADOW", "PAPER_REAL_MD"]
ScenarioStatus = Literal["OK", "FAILED", "SKIPPED"]
SessionStatus = Literal["OPEN", "CLOSED"]


class ScenarioSpec(_ContractModel):
    """固定 E2E 场景规格；默认注入 TargetPosition，不依赖 Qlib。"""

    scenario_id: str
    title: str = ""
    fixture_id: str = ""
    default_mode: E2EMode = "PAPER"
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


class VirtualOrder(_ContractModel):
    """Shadow 模式：Would-Submit 虚拟订单。"""

    virtual_order_id: str
    instrument_key: str
    side: str = "BUY"
    quantity: float = 0.0
    status: str = "WOULD_SUBMIT"
    trace_id: str = ""
    scenario_run_id: str = ""
    session_id: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenarioResult(_ContractModel):
    """单次场景运行结果。"""

    scenario_run_id: str
    scenario_id: str
    run_id: str = ""
    session_id: str = ""
    mode: E2EMode = "PAPER"
    status: ScenarioStatus = "OK"
    trace_id: str = ""
    dataset_hash: str = ""
    strategy_version: str = ""
    strategy_id: str = ""
    intent_fingerprint: str = ""
    apply_id: str = ""
    risk_run_id: str = ""
    risk_verdict: str = ""
    order_ids: list[str] = Field(default_factory=list)
    virtual_orders: list[VirtualOrder] = Field(default_factory=list)
    reconciliation_run_id: str = ""
    reconciliation_critical: bool = False
    blocked_by_safety: bool = False
    messages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TradingSession(_ContractModel):
    """交易日 Session：关联 account / dataset / 场景运行。"""

    session_id: str
    trading_date: str = ""
    market: str = "US"
    mode: E2EMode = "PAPER"
    status: SessionStatus = "OPEN"
    account_id: str = ""
    portfolio_id: str = ""
    dataset_hash: str = ""
    strategy_version: str = ""
    strategy_id: str = ""
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    scenario_run_ids: list[str] = Field(default_factory=list)
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConsistencyScore(_ContractModel):
    """E2E 完成度评分（0~1）。"""

    score_id: str
    run_id: str = ""
    session_id: str = ""
    signal_consistency: float = 0.0
    order_consistency: float = 0.0
    execution_consistency: float = 0.0
    position_consistency: float = 0.0
    reconciliation_score: float = 0.0
    audit_coverage: float = 0.0
    safety_coverage: float = 0.0
    overall: float = 0.0
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayRequest(_ContractModel):
    """确定性 Replay 请求。"""

    dataset_hash: str
    strategy_version: str
    fixture_id: str = ""
    scenario_id: str = "E2E-001"
    config: dict[str, Any] = Field(default_factory=dict)
    mode: E2EMode = "PAPER"


class ReplayResult(_ContractModel):
    """两次运行 intent 指纹比对。"""

    ok: bool = False
    first_fingerprint: str = ""
    second_fingerprint: str = ""
    drift_detected: bool = False
    messages: list[str] = Field(default_factory=list)


class ComparisonSummary(_ContractModel):
    """Paper vs Shadow 摘要对比。"""

    paper_run_id: str = ""
    shadow_run_id: str = ""
    intent_match: bool = False
    target_count_paper: int = 0
    target_count_shadow: int = 0
    virtual_order_count: int = 0
    messages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class E2ERunPayload(_ContractModel):
    """R2 持久化的场景明细。"""

    scenario_result: ScenarioResult
    targets: list[TargetPosition] = Field(default_factory=list)
    engine_version: str = ENGINE_VERSION
