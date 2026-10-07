"""Phase 8E：Live Performance Feedback 契约（只观察，不改 LIVE / Version）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_live_performance_feedback@1"

BaselineType = Literal[
    "BACKTEST",
    "SHADOW",
    "CONTROLLED_LIVE",
    "PROMOTION_BASELINE",
]
ActualSource = Literal["SHADOW", "CONTROLLED_LIVE", "LIVE"]
ComparisonRunStatus = Literal[
    "CREATED",
    "COLLECTING",
    "COMPUTING",
    "ATTRIBUTING",
    "EVALUATED",
    "PUBLISHED",
    "FAILED",
]
DriftSeverity = Literal["OK", "WARNING", "CRITICAL", "SKIP"]
DriftAction = Literal["ALERT"]
DriftType = Literal[
    "DATA_DRIFT",
    "FEATURE_DRIFT",
    "MODEL_DRIFT",
    "SIGNAL_DRIFT",
    "UNIVERSE_DRIFT",
    "PORTFOLIO_DRIFT",
    "RISK_DRIFT",
    "EXECUTION_DRIFT",
    "SLIPPAGE_DRIFT",
    "COST_DRIFT",
    "CAPACITY_DRIFT",
    "MARKET_REGIME_DRIFT",
]


class _FbModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MetricsSnapshot(_FbModel):
    """六类指标摘要（Return / Risk / Portfolio / Execution / Cost / Signal）。"""

    return_total: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    turnover: float = 0.0
    gross_exposure: float = 0.0
    slippage_bps: float = 0.0
    total_cost_bps: float = 0.0
    reject_rate: float = 0.0
    signal_correlation: float = 1.0
    qty_delta: float = 0.0
    shadow_drift: float = 0.0
    extra: dict[str, Any] = Field(default_factory=dict)


class DriftPolicyRule(_FbModel):
    """单指标漂移规则；action 固定 ALERT（不触发环境变更）。"""

    metric: str
    window: str = "7d"
    warning_threshold: float = 0.05
    critical_threshold: float = 0.12
    min_observation_count: int = 1
    consecutive_breach_count: int = 1
    action: DriftAction = "ALERT"


class DriftPolicyRecord(_FbModel):
    """DriftPolicy SSOT（版本化 + content_hash 钉扎）。"""

    policy_id: str
    policy_version: str
    policy_content_hash: str
    rules: list[DriftPolicyRule] = Field(default_factory=list)
    engine_version: str = ENGINE_VERSION
    description: str = ""


class ExpectedBaseline(_FbModel):
    """晋级后冻结的预期基线（immutable）。"""

    baseline_id: str
    strategy_code: str
    strategy_version: str
    content_hash: str
    candidate_id: str = ""
    validation_id: str = ""
    pipeline_run_id: str = ""
    dataset_hash: str = ""
    snapshot_id: str = ""
    model_version: str = ""
    feature_version: str = ""
    backtest_hash: str = ""
    baseline_type: BaselineType = "PROMOTION_BASELINE"
    metrics_snapshot: MetricsSnapshot = Field(default_factory=MetricsSnapshot)
    drift_policy_id: str = ""
    drift_policy_version: str = ""
    drift_policy_content_hash: str = ""
    immutable: bool = True
    created_at: str = ""
    storage_uri: str = ""


class MetricDeviation(_FbModel):
    metric: str
    baseline: float
    actual: float
    delta: float
    rel_delta: float = 0.0
    severity: DriftSeverity = "OK"


class DriftFinding(_FbModel):
    drift_type: DriftType
    severity: DriftSeverity = "OK"
    metric: str = ""
    message: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)


class ReturnAttribution(_FbModel):
    """简化收益归因分解。"""

    alpha_bps: float = 0.0
    beta_bps: float = 0.0
    cost_bps: float = 0.0
    slippage_bps: float = 0.0
    timing_bps: float = 0.0
    residual_bps: float = 0.0


class ProductionDriftReport(_FbModel):
    report_id: str
    run_id: str
    baseline_id: str
    strategy_code: str
    actual_source: ActualSource
    window_start: str = ""
    window_end: str = ""
    policy_content_hash: str = ""
    deviations: list[MetricDeviation] = Field(default_factory=list)
    findings: list[DriftFinding] = Field(default_factory=list)
    attribution: ReturnAttribution = Field(default_factory=ReturnAttribution)
    overall_severity: DriftSeverity = "OK"
    created_at: str = ""


class PerformanceComparisonRun(_FbModel):
    """基线 vs 实际表现对比 Run（FSM，不改 Strategy lifecycle）。"""

    run_id: str
    strategy_code: str
    baseline_id: str
    actual_source: ActualSource
    window_start: str = ""
    window_end: str = ""
    idempotency_key: str = ""
    status: ComparisonRunStatus = "CREATED"
    policy_id: str = ""
    policy_version: str = ""
    policy_content_hash: str = ""
    actual_metrics: MetricsSnapshot = Field(default_factory=MetricsSnapshot)
    deviations: list[MetricDeviation] = Field(default_factory=list)
    findings: list[DriftFinding] = Field(default_factory=list)
    report_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    storage_uri: str = ""


__all__ = [
    "ENGINE_VERSION",
    "ActualSource",
    "BaselineType",
    "ComparisonRunStatus",
    "DriftAction",
    "DriftFinding",
    "DriftPolicyRecord",
    "DriftPolicyRule",
    "DriftSeverity",
    "DriftType",
    "ExpectedBaseline",
    "MetricDeviation",
    "MetricsSnapshot",
    "PerformanceComparisonRun",
    "ProductionDriftReport",
    "ReturnAttribution",
]
