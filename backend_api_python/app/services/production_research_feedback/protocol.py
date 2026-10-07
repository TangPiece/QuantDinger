"""Phase 8H：Production → Research Feedback Loop 契约（禁止直读 Trading DB）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "qd_production_research_feedback@1"

FeedbackType = Literal[
    "SIGNAL_FEEDBACK",
    "EXECUTION_FEEDBACK",
    "PORTFOLIO_FEEDBACK",
    "RISK_FEEDBACK",
    "PERFORMANCE_FEEDBACK",
    "DRIFT_FEEDBACK",
    "FAILURE_CASE",
]
RealityKind = Literal["ACTUAL", "COUNTERFACTUAL"]
HypothesisStatus = Literal["DRAFT", "TESTING", "SUPPORTED", "REJECTED", "ARCHIVED"]
QualityGateVerdict = Literal["PASS", "REJECT"]


class _FbModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FeedbackRow(_FbModel):
    """单条反馈观测（不含 Counterfactual 模拟 PnL）。"""

    row_id: str = ""
    metric: str = ""
    value: float = 0.0
    as_of_time: str = ""
    source_artifact_id: str = ""
    source_phase: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackLineage(_FbModel):
    """8E/8F/8G 工件 lineage（只读引用）。"""

    comparison_run_id: str = ""
    drift_report_id: str = ""
    alert_id: str = ""
    incident_id: str = ""
    governance_decision_id: str = ""
    dataset_hash: str = ""
    snapshot_id: str = ""
    model_version: str = ""
    strategy_version: str = ""


class ProductionFeedbackDataset(_FbModel):
    """经 QualityGate 后的不可变反馈数据集。"""

    dataset_id: str
    strategy_code: str
    feedback_type: FeedbackType
    dataset_hash: str
    schema_version: str = "pf_schema@1"
    filter_spec: dict[str, Any] = Field(default_factory=dict)
    window_start: str = ""
    window_end: str = ""
    processor_id: str = "pf_processor@1"
    processor_version: str = "1"
    rows: list[FeedbackRow] = Field(default_factory=list)
    lineage: FeedbackLineage = Field(default_factory=FeedbackLineage)
    quality_gate_verdict: QualityGateVerdict = "PASS"
    created_at: str = ""
    session_id: str = ""
    storage_uri: str = ""
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class PnlSummary(_FbModel):
    """Actual PnL 摘要（Counterfactual 不得写入此结构）。"""

    pnl_total: float = 0.0
    currency: str = "CNY"
    as_of_time: str = ""


class ProductionRealitySnapshot(_FbModel):
    """生产现实快照（immutable；修正 → 新版本 + supersedes_snapshot_id）。"""

    snapshot_id: str
    snapshot_version: int = 1
    supersedes_snapshot_id: str = ""
    strategy_code: str
    reality_kind: RealityKind = "ACTUAL"
    as_of_time: str = ""
    pnl_summary: PnlSummary = Field(default_factory=PnlSummary)
    metrics: dict[str, float] = Field(default_factory=dict)
    dataset_id: str = ""
    lineage: FeedbackLineage = Field(default_factory=FeedbackLineage)
    content_hash: str = ""
    created_at: str = ""
    session_id: str = ""
    storage_uri: str = ""
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchFailureCase(_FbModel):
    """失败案例（链 incident / governance / lineage hashes）。"""

    case_id: str
    strategy_code: str
    incident_id: str = ""
    governance_decision_id: str = ""
    dataset_hash: str = ""
    feedback_dataset_id: str = ""
    category: str = "SYSTEM"
    severity: str = "CRITICAL"
    summary: str = ""
    lineage: FeedbackLineage = Field(default_factory=FeedbackLineage)
    created_at: str = ""
    session_id: str = ""
    storage_uri: str = ""
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchHypothesis(_FbModel):
    """由 FailureCase 衍生的研究假设（不触发训练）。"""

    hypothesis_id: str
    strategy_code: str
    status: HypothesisStatus = "DRAFT"
    failure_case_ids: list[str] = Field(default_factory=list)
    feedback_dataset_id: str = ""
    title: str = ""
    description: str = ""
    created_at: str = ""
    session_id: str = ""
    storage_uri: str = ""
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackExperimentLink(_FbModel):
    """Experiment lineage 钉扎（parent_*；不跑训练）。"""

    link_id: str
    experiment_id: str
    strategy_code: str
    parent_feedback_dataset_id: str = ""
    parent_failure_case_ids: list[str] = Field(default_factory=list)
    parent_incident_ids: list[str] = Field(default_factory=list)
    hypothesis_id: str = ""
    created_at: str = ""
    session_id: str = ""
    storage_uri: str = ""
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchFeedbackQuery(_FbModel):
    """ResearchFeedbackQuery 只读查询（默认 Actual 桶）。"""

    strategy_code: str = ""
    feedback_type: FeedbackType | str = ""
    dataset_id: str = ""
    window_start: str = ""
    window_end: str = ""
    reality_kind: RealityKind = "ACTUAL"
    limit: int = 100


class ResearchFeedbackRecord(_FbModel):
    """统一查询结果行。"""

    record_kind: Literal["DATASET", "SNAPSHOT", "FAILURE_CASE", "COUNTERFACTUAL"]
    strategy_code: str
    dataset_id: str = ""
    snapshot_id: str = ""
    case_id: str = ""
    feedback_type: str = ""
    reality_kind: RealityKind = "ACTUAL"
    dataset_hash: str = ""
    as_of_time: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class CounterfactualRecord(_FbModel):
    """Counterfactual 模拟摘要（与 Actual PnL 严格分桶）。"""

    record_id: str
    parent_snapshot_id: str
    strategy_code: str
    reality_kind: RealityKind = "COUNTERFACTUAL"
    scenario: dict[str, Any] = Field(default_factory=dict)
    simulated_summary: dict[str, float] = Field(default_factory=dict)
    created_at: str = ""
    session_id: str = ""
    storage_uri: str = ""
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualityGateResult(_FbModel):
    verdict: QualityGateVerdict
    reasons: list[str] = Field(default_factory=list)


__all__ = [
    "ENGINE_VERSION",
    "CounterfactualRecord",
    "FeedbackExperimentLink",
    "FeedbackLineage",
    "FeedbackRow",
    "FeedbackType",
    "HypothesisStatus",
    "PnlSummary",
    "ProductionFeedbackDataset",
    "ProductionRealitySnapshot",
    "QualityGateResult",
    "QualityGateVerdict",
    "RealityKind",
    "ResearchFailureCase",
    "ResearchFeedbackQuery",
    "ResearchFeedbackRecord",
    "ResearchHypothesis",
]
