"""研究 Domain Contract（Pydantic），对齐 docs/data/phase1/05_contracts.md。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _ContractModel(BaseModel):
    """研究契约基类：禁多余字段，便于跨引擎稳定序列化。"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class AssetType(str, Enum):
    STOCK = "STOCK"
    ETF = "ETF"
    INDEX = "INDEX"
    FUND = "FUND"
    FUTURE = "FUTURE"
    OPTION = "OPTION"
    CRYPTO = "CRYPTO"
    FX = "FX"


class InstrumentKey(_ContractModel):
    """规范研究标的键：'{market}:{symbol}'。"""

    market: str
    symbol: str

    def as_key(self) -> str:
        return f"{self.market}:{self.symbol}"

    @classmethod
    def parse(cls, value: str) -> "InstrumentKey":
        """从 'market:symbol' 解析；符号本身可含冒号时取首段为 market。"""
        text = str(value or "").strip()
        if ":" not in text:
            raise ValueError(f"invalid instrument_key: {value!r}")
        market, symbol = text.split(":", 1)
        return cls(market=market, symbol=symbol)


class PricePolicy(_ContractModel):
    """查询时复权政策；Canonical 始终存 raw。"""

    adjustment: Literal["none", "pre", "post"] = "none"
    return_type: Literal["price", "total"] = "price"


class KnowledgeTime(_ContractModel):
    """回测信息截止时刻。"""

    value: datetime


class FeatureDefinition(_ContractModel):
    """研究 Feature / Factor 定义（Factor 为研究语义扩展；交易侧 FactorDefinition 无关）。

    Phase 4A：补齐类型、引擎、PIT 政策、factor_hash；值在 R2，不进 D1。
    """

    code: str
    version: str
    name: str
    expression: str
    frequency: str = "1d"
    dependencies: list[str] = Field(default_factory=list)
    backend: Literal["r2_factor", "d1_l2_factors", "computed"] = "r2_factor"
    online_supported: bool = False
    definition: dict[str, Any] = Field(default_factory=dict)
    # Phase 4A Factor Lab
    description: str = ""
    factor_type: Literal[
        "TECHNICAL",
        "FUNDAMENTAL",
        "MICROSTRUCTURE",
        "LEVEL2",
        "ALTERNATIVE",
        "ML_DERIVED",
        "COMPOSITE",
        "CUSTOM",
    ] = "CUSTOM"
    computation_engine: Literal[
        "qlib", "quantdinger", "duckdb", "polars", "level2"
    ] = "quantdinger"
    engine_version: str = ""
    universe: Optional[str] = None
    information_policy: Literal["PIT_SAFE", "NON_PIT", "UNKNOWN"] = "UNKNOWN"
    schema_version: str = "factor_daily_long@1"
    factor_hash: Optional[str] = None
    price_policy: Optional[PricePolicy] = None
    processor_ref: Optional[str] = None


class LabelDefinition(_ContractModel):
    code: str
    version: str
    name: str
    expression: str
    horizon: Optional[int] = None
    definition: dict[str, Any] = Field(default_factory=dict)


class ProcessorDefinition(_ContractModel):
    code: str
    version: str
    pipeline: list[dict[str, Any]]


class DatasetDefinition(_ContractModel):
    code: str
    version: str
    name: str
    frequency: str
    universe_code: str
    universe_version: str
    snapshot_id: str
    schema_version: str
    features: list[str]
    label: Optional[LabelDefinition] = None
    processor: Optional[str] = None
    price_policy: PricePolicy = Field(default_factory=PricePolicy)
    pit: bool = True


class DataVersionRef(_ContractModel):
    dataset_code: str
    version: str
    checksum: Optional[str] = None
    r2_uri: Optional[str] = None


class SnapshotRef(_ContractModel):
    snapshot_id: str
    items: list[DataVersionRef] = Field(default_factory=list)


class DatasetHandle(_ContractModel):
    definition: DatasetDefinition
    snapshot: SnapshotRef
    dataset_hash: str
    manifest_uri: str = ""


class ModelDefinition(_ContractModel):
    """可版本化的模型资产（Phase 2D：仅 LightGBM 引擎）。"""

    code: str
    version: str
    name: str
    engine: Literal["lightgbm"] = "lightgbm"
    config: dict[str, Any] = Field(default_factory=dict)


class PredictionRecord(_ContractModel):
    """Test 段预测行；不含 Signal / 订单语义。"""

    instrument_key: str
    trading_date: str
    prediction: float
    model_version: str
    dataset_hash: str
    bundle_hash: str
    # 确定性行 id：sha256(model_version|instrument|trading_date|dataset_hash)
    prediction_id: str = ""
    snapshot_id: str = ""
    created_at: Optional[datetime] = None


class ArtifactRecord(_ContractModel):
    """D1 / Registry 中的 artifact 索引（大文件在 R2 或本地 cache）。"""

    artifact_id: str
    artifact_type: str
    storage_uri: str
    checksum: Optional[str] = None
    size_bytes: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelVersionRecord(_ContractModel):
    """model_version 行：挂 dataset / processor / artifact。"""

    model_code: str
    version: str
    config: dict[str, Any] = Field(default_factory=dict)
    artifact_id: Optional[str] = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    dataset_ref: Optional[str] = None
    processor_ref: Optional[str] = None


class ModelArtifact(_ContractModel):
    model_code: str
    version: str
    engine: str
    dataset_ref: str
    processor_ref: Optional[str] = None
    artifact_uri: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class ExperimentDefinition(_ContractModel):
    """研究实验顶层对象（Domain 元数据 + 引用；大数据在 artifact/manifest）。"""

    experiment_id: str
    name: str
    dataset_ref: str
    snapshot_id: str
    dataset_hash: str
    model_version_ref: Optional[str] = None
    mlflow_run_id: Optional[str] = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    feature_refs: list[str] = Field(default_factory=list)
    processor_ref: Optional[str] = None
    strategy_version: Optional[str] = None
    model_artifact_id: Optional[str] = None
    signal_artifact_id: Optional[str] = None
    signal_run_id: Optional[str] = None
    bundle_hash: Optional[str] = None
    prediction_fingerprint: Optional[str] = None
    repro_fingerprint: Optional[str] = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    manifest_uri: str = ""
    status: Literal["COMPLETED", "FAILED"] = "COMPLETED"
    segments: dict[str, Any] = Field(default_factory=dict)


class ExperimentManifest(_ContractModel):
    """实验快照（落盘 JSON）；非 SSOT，定义仍以 Registry 为准。"""

    experiment_id: str
    name: str
    experiment_pipeline_version: str
    repro_fingerprint: str
    dataset_ref: str
    dataset_hash: str
    bundle_hash: str
    snapshot_id: str
    feature_refs: list[str] = Field(default_factory=list)
    processor_ref: Optional[str] = None
    model: dict[str, Any] = Field(default_factory=dict)
    strategy: dict[str, Any] = Field(default_factory=dict)
    portfolio: dict[str, Any] = Field(default_factory=dict)
    segments: dict[str, Any] = Field(default_factory=dict)
    model_artifact_id: str = ""
    model_artifact_uri: str = ""
    signal_artifact_id: str = ""
    signal_artifact_uri: str = ""
    signal_run_id: str = ""
    prediction_fingerprint: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    mlflow_run_id: Optional[str] = None
    seed: int = 42


class Signal(_ContractModel):
    """研究域信号：Prediction 经 SignalStrategy 解释后的意图（非订单）。"""

    signal_id: str
    instrument_key: str
    trading_date: str
    direction: Literal["LONG", "SHORT", "FLAT"]
    score: float
    # 信号生成时刻 / PIT 截止 / 计划可执行时刻（均须 timezone-aware UTC）
    signal_time: datetime
    knowledge_time: datetime
    execution_time: datetime
    rank: Optional[int] = None
    confidence: Optional[float] = None
    target_weight: Optional[float] = None
    model_version: str = ""
    strategy_version: str = ""
    dataset_hash: str = ""
    bundle_hash: Optional[str] = None


class TargetPosition(_ContractModel):
    """组合构建后的目标仓位；不含 Broker / 撮合。"""

    instrument_key: str
    trading_date: str
    portfolio_id: str
    strategy_version: str
    dataset_hash: str
    # 与 Signal.signal_time 对齐，便于下游衔接
    timestamp: datetime
    target_weight: Optional[float] = None
    target_quantity: Optional[float] = None
    signal_id: Optional[str] = None


class OrderIntent(_ContractModel):
    """订单意图契约；2E 占位 mapper / 3C 再平衡正式使用（不接 Broker）。"""

    instrument_key: str
    side: Literal["BUY", "SELL"]
    quantity: float
    urgency: Literal["LOW", "NORMAL", "HIGH"] = "NORMAL"
    execution_algorithm: Literal["MARKET", "LIMIT", "TWAP", "VWAP", "POV", "CUSTOM"] = "MARKET"
    limit_price: Optional[float] = None
    signal_id: Optional[str] = None
    strategy_version: Optional[str] = None
    trading_date: Optional[str] = None
    # Phase 3C：再平衡审计字段（可选，向后兼容）
    target_quantity: Optional[float] = None
    current_quantity: Optional[float] = None
    quantity_delta: Optional[float] = None
    signal_time: Optional[datetime] = None
    intended_execution_time: Optional[datetime] = None
    reason: Optional[str] = None
    # Phase 6H：贯穿 Signal→Fill 的可追溯 id
    trace_id: Optional[str] = None


class SignalRunRecord(_ContractModel):
    """一次 Prediction→Signal→TargetPosition 运行的 Registry 索引。"""

    signal_run_id: str
    strategy_version: str
    prediction_fingerprint: str
    artifact_id: str
    storage_uri: str
    cash_weight: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConsistencyRunRecord(_ContractModel):
    """Phase 3E：双引擎一致性运行的 Registry 索引（大数据在 R2 artifact）。"""

    run_id: str
    dataset_hash: str
    qlib_result_id: Optional[str] = None
    qd_result_id: Optional[str] = None
    status: Literal["PASSED", "FAILED", "SKIPPED_QLIB"] = "PASSED"
    max_equity_diff: Optional[float] = None
    max_position_diff: Optional[float] = None
    artifact_uri: str = ""
    level: str = ""
    semantic_fingerprint: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorDatasetRecord(_ContractModel):
    """Phase 4A：因子计算结果集的 Registry 索引（数值在 R2 Parquet）。"""

    factor_dataset_id: str
    factor_ref: str
    factor_hash: str
    dataset_hash: str
    snapshot_id: str
    universe_code: str = ""
    frequency: str = "1d"
    start_date: str = ""
    end_date: str = ""
    storage_uri: str = ""
    checksum: Optional[str] = None
    row_count: Optional[int] = None
    layout: Literal["long", "wide"] = "long"
    schema_version: str = "factor_daily_long@1"
    status: Literal["ACTIVE", "FAILED"] = "ACTIVE"
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationDatasetRecord(_ContractModel):
    """Phase 4C：评价面板 Registry 索引（明细在 R2；D1 仅存元数据）。"""

    evaluation_hash: str
    factor_dataset_id: str
    factor_dataset_hash: str
    snapshot_id: str
    universe_code: str = ""
    universe_version: str = ""
    start_date: str = ""
    end_date: str = ""
    return_spec: dict[str, Any] = Field(default_factory=dict)
    price_policy: Optional["PricePolicy"] = None
    evaluator_version: str = "qd_factor_eval@1"
    mode: Literal["CROSS_SECTIONAL", "TIME_SERIES"] = "CROSS_SECTIONAL"
    storage_uri: str = ""
    checksum: Optional[str] = None
    row_count: Optional[int] = None
    schema_version: str = "evaluation_panel@1"
    status: Literal["ACTIVE", "FAILED"] = "ACTIVE"
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorEvaluationSummary(_ContractModel):
    """Phase 4D：按 horizon 的 IC/RankIC 汇总（明细时间序列在 R2）。"""

    metric_hash: str
    evaluation_hash: str
    factor_dataset_id: str = ""
    horizon: int
    mean_ic: Optional[float] = None
    median_ic: Optional[float] = None
    std_ic: Optional[float] = None
    min_ic: Optional[float] = None
    max_ic: Optional[float] = None
    ic_ir: Optional[float] = None
    ic_t_stat: Optional[float] = None
    positive_ic_ratio: Optional[float] = None
    mean_rank_ic: Optional[float] = None
    median_rank_ic: Optional[float] = None
    std_rank_ic: Optional[float] = None
    min_rank_ic: Optional[float] = None
    max_rank_ic: Optional[float] = None
    rank_ic_ir: Optional[float] = None
    rank_ic_t_stat: Optional[float] = None
    positive_rank_ic_ratio: Optional[float] = None
    valid_day_count: int = 0
    total_day_count: int = 0
    direction: Literal["AUTO", "POSITIVE", "NEGATIVE"] = "AUTO"
    metric_version: str = "qd_factor_metrics@1"
    storage_uri: str = ""
    checksum: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GroupEvaluationSummary(_ContractModel):
    """Phase 4E：分位组合 / 换手 / 成本估算汇总（明细在 R2）。"""

    group_evaluation_hash: str
    evaluation_hash: str
    factor_dataset_id: str = ""
    horizon: int
    group_count: int = 10
    weighting_method: str = "EQUAL_WEIGHT"
    direction: Literal["POSITIVE", "NEGATIVE"] = "POSITIVE"
    portfolio_mode: str = "BOTH"
    long_group: int = 1
    short_group: int = 10
    mean_long_return: Optional[float] = None
    mean_short_return: Optional[float] = None
    mean_long_short_return: Optional[float] = None
    mean_turnover: Optional[float] = None
    mean_estimated_cost: Optional[float] = None
    mean_net_long_short_return: Optional[float] = None
    valid_day_count: int = 0
    total_day_count: int = 0
    group_version: str = "qd_factor_groups@1"
    storage_uri: str = ""
    checksum: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorStabilitySummary(_ContractModel):
    """Phase 4F：稳定性 / Decay 汇总（明细在 R2；无综合 score）。"""

    stability_hash: str
    evaluation_hash: str
    factor_dataset_id: str = ""
    horizon: int
    rolling_windows_json: list[Any] = Field(default_factory=list)
    decay_summary_json: list[Any] = Field(default_factory=list)
    regime_summary_json: list[Any] = Field(default_factory=list)
    ic_stability_metrics_json: dict[str, Any] = Field(default_factory=dict)
    group_stability_metrics_json: dict[str, Any] = Field(default_factory=dict)
    stability_version: str = "qd_factor_stability@1"
    storage_uri: str = ""
    checksum: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorNeutralizationSummary(_ContractModel):
    """Phase 4G：中性化汇总（明细在 R2；Raw Factor 不可变）。"""

    neutralization_hash: str
    factor_dataset_id: str
    factor_dataset_hash: str = ""
    method: str = "REGRESSION"
    targets_json: list[Any] = Field(default_factory=list)
    r_squared_mean: Optional[float] = None
    diagnostics_json: dict[str, Any] = Field(default_factory=dict)
    neutralized_factor_dataset_id: str = ""
    neutralization_version: str = "qd_factor_neutralization@1"
    storage_uri: str = ""
    checksum: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorCombinationSummary(_ContractModel):
    """Phase 4H：因子组合汇总（明细在 R2；成员 Dataset 不可变）。"""

    combination_hash: str
    member_factor_dataset_ids_json: list[Any] = Field(default_factory=list)
    normalize: str = "RANK"
    weight_method: str = "EQUAL"
    weights_json: dict[str, Any] = Field(default_factory=dict)
    correlation_summary_json: dict[str, Any] = Field(default_factory=dict)
    redundancy_pairs_json: list[Any] = Field(default_factory=list)
    composite_factor_dataset_id: str = ""
    combination_version: str = "qd_factor_combination@1"
    storage_uri: str = ""
    checksum: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FactorPortfolioSummary(_ContractModel):
    """Phase 4I：因子组合（持仓）汇总；明细在 R2，非 Production Backtest。"""

    portfolio_hash: str
    factor_dataset_id: str
    evaluation_hash: str = ""
    construction_method: str = "LONG_ONLY"
    weight_method: str = "EQUAL_WEIGHT"
    rebalance_frequency: str = "DAILY"
    selection_json: dict[str, Any] = Field(default_factory=dict)
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    portfolio_version: str = "qd_factor_portfolio@1"
    storage_uri: str = ""
    checksum: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchStrategyRecord(_ContractModel):
    """Phase 5A：研究策略名录（逻辑 code，非交易 Strategy API V2）。"""

    strategy_code: str
    name: str = ""
    description: str = ""
    status: str = "ACTIVE"
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyResearchSummary(_ContractModel):
    """Phase 5A：冻结策略版本汇总；明细在 R2，不算收益。"""

    strategy_hash: str
    strategy_code: str
    strategy_version_label: str = "qd_strategy_research@1"
    factor_dataset_id: str = ""
    portfolio_hash: str = ""
    evaluation_hash: str = ""
    signal_definition_json: dict[str, Any] = Field(default_factory=dict)
    rebalance_rule_json: dict[str, Any] = Field(default_factory=dict)
    holding_rule_json: dict[str, Any] = Field(default_factory=dict)
    universe_code: str = ""
    snapshot_id: str = ""
    signal_row_count: int = 0
    position_row_count: int = 0
    storage_uri: str = ""
    checksum: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchBacktestSummary(_ContractModel):
    """Phase 5B/5C：研究回测汇总；日明细在 R2，D1 仅 Summary。"""

    backtest_hash: str
    strategy_hash: str
    start_date: str
    end_date: str
    execution_policy: str = "NEXT_OPEN"
    benchmark_mode: str = "NONE"
    benchmark_instrument_key: str = ""
    realism: str = "GROSS"
    market_rule: str = ""
    execution_profile_version: str = "qd_research_execution@1"
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    benchmark_metrics_json: dict[str, Any] = Field(default_factory=dict)
    attribution_json: dict[str, Any] = Field(default_factory=dict)
    engine_version: str = "qd_research_backtest@1"
    return_calculation_version: str = "research_nav@1"
    storage_uri: str = ""
    checksum: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class QlibRunSummary(_ContractModel):
    """Phase 5D：Qlib Strategy Adapter 运行汇总；明细在 R2。"""

    qlib_run_hash: str
    strategy_hash: str
    start_date: str
    end_date: str
    execution_policy: str = "NEXT_OPEN"
    realism: str = "GROSS"
    market_rule: str = ""
    dataset_ref: str = ""
    dataset_hash: str = ""
    materialization_id: str = ""
    backtest_hash: str = ""
    compatibility_json: dict[str, Any] = Field(default_factory=dict)
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    engine_version: str = "qlib_strategy_adapter@1"
    recorder_id: str = ""
    storage_uri: str = ""
    checksum: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrossValidationSummary(_ContractModel):
    """Phase 5E：双引擎交叉验证汇总；明细在 R2。"""

    cv_hash: str
    strategy_hash: str
    backtest_hash: str = ""
    qlib_run_hash: str = ""
    start_date: str = ""
    end_date: str = ""
    realism: str = "GROSS"
    execution_policy: str = "NEXT_OPEN"
    status: str = "FAILED"
    layer_results_json: dict[str, Any] = Field(default_factory=dict)
    attribution_json: dict[str, Any] = Field(default_factory=dict)
    metrics_side_by_side_json: dict[str, Any] = Field(default_factory=dict)
    engine_version: str = "qd_cross_validation@1"
    storage_uri: str = ""
    checksum: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionBundleSummary(_ContractModel):
    """Phase 5F：生产 Bundle 冻结汇总；明细在 R2。

    注意：字段 ``bundle_hash`` 是 *production* bundle 身份，
    勿与 2A ``ResearchBundleIdentity.bundle_hash`` 混淆。
    """

    bundle_hash: str
    strategy_hash: str
    strategy_code: str = ""
    cv_hash: str = ""
    backtest_hash: str = ""
    qlib_run_hash: str = ""
    dataset_hash: str = ""
    materialization_id: str = ""
    model_artifact_id: str = ""
    model_version: str = ""
    processor_hash: str = ""
    processor_artifact_uri: str = ""
    pipeline_digest: str = ""
    universe_code: str = ""
    snapshot_id: str = ""
    execution_policy: str = "NEXT_OPEN"
    realism: str = "GROSS"
    market_rule: str = ""
    status: str = "DRAFT"
    parent_bundle_hash: str = ""
    dependency_lock_json: dict[str, Any] = Field(default_factory=dict)
    feature_hashes: list[str] = Field(default_factory=list)
    engine_version: str = "qd_production_bridge@1"
    storage_uri: str = ""
    checksum: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionDeploymentSummary(_ContractModel):
    """Phase 5F：某 strategy_code 当前/历史部署指针。"""

    deployment_id: str
    bundle_hash: str
    strategy_code: str
    status: str = "DEPLOYED"
    previous_bundle_hash: str = ""
    deployed_at: Optional[str] = None
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionDeploymentRunSummary(_ContractModel):
    """Phase 5F：干跑 Inference 审计。"""

    run_id: str
    bundle_hash: str
    deployment_id: str = ""
    trading_date: str = ""
    status: str = "OK"
    n_signals: int = 0
    n_intents: int = 0
    gate_json: dict[str, Any] = Field(default_factory=dict)
    storage_uri: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionRuntimeSummary(_ContractModel):
    """Phase 6A：Production Runtime 实例汇总。"""

    runtime_id: str
    bundle_hash: str
    strategy_code: str = ""
    market: str = "CN_A"
    environment: str = "PAPER"
    status: str = "STARTING"
    session_phase: str = "PRE_MARKET"
    trading_date: str = ""
    started_at: Optional[str] = None
    last_heartbeat: Optional[str] = None
    engine_version: str = "qd_production_runtime@1"
    storage_uri: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionRuntimeEventRecord(_ContractModel):
    """Phase 6A：Runtime 事件日志行。"""

    event_id: str
    runtime_id: str
    event_type: str
    trading_date: str = ""
    session_phase: str = ""
    message: str = ""
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class ProductionRuntimeRunSummary(_ContractModel):
    """Phase 6A：幂等 tick / inference run。"""

    run_id: str
    runtime_id: str
    bundle_hash: str
    idempotency_key: str
    trading_date: str = ""
    session_phase: str = ""
    status: str = "OK"
    n_signals: int = 0
    n_intents: int = 0
    bridge_run_id: str = ""
    storage_uri: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionAccountSummary(_ContractModel):
    """Phase 6B：生产账户 Registry 行。"""

    account_id: str
    environment: str = "PAPER"
    market: str = "CN_A"
    status: str = "ACTIVE"
    currency: str = "CNY"
    available_cash: float = 0.0
    frozen_cash: float = 0.0
    market_value: float = 0.0
    equity: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    engine_version: str = "qd_portfolio_service@1"
    storage_uri: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionPortfolioSummary(_ContractModel):
    """Phase 6B：组合 Registry 行。"""

    portfolio_id: str
    account_id: str
    runtime_id: str = ""
    bundle_hash: str = ""
    status: str = "ACTIVE"
    trading_date: str = ""
    engine_version: str = "qd_portfolio_service@1"
    storage_uri: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionPositionSummary(_ContractModel):
    """Phase 6B：当前持仓态 Registry 行。"""

    portfolio_id: str
    instrument_key: str
    quantity: float = 0.0
    available_quantity: float = 0.0
    frozen_quantity: float = 0.0
    avg_cost: float = 0.0
    market_value: float = 0.0
    currency: str = "CNY"
    as_of: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionPositionEventRecord(_ContractModel):
    """Phase 6B：持仓事件日志行。"""

    event_id: str
    portfolio_id: str
    account_id: str = ""
    event_type: str
    instrument_key: str = ""
    trading_date: str = ""
    quantity: float = 0.0
    price: float = 0.0
    cash_delta: float = 0.0
    fee: float = 0.0
    idempotency_key: str = ""
    message: str = ""
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class ProductionPortfolioSnapshotSummary(_ContractModel):
    """Phase 6B：组合快照元数据。"""

    snapshot_id: str
    account_id: str
    portfolio_id: str
    trading_date: str = ""
    knowledge_time: Optional[str] = None
    cash: float = 0.0
    market_value: float = 0.0
    equity: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    runtime_id: str = ""
    bundle_hash: str = ""
    idempotency_key: str = ""
    storage_uri: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductionPortfolioApplySummary(_ContractModel):
    """Phase 6B：幂等 apply_targets 运行。"""

    apply_id: str
    account_id: str
    portfolio_id: str
    idempotency_key: str
    trading_date: str = ""
    status: str = "OK"
    n_deltas: int = 0
    n_events: int = 0
    snapshot_id: str = ""
    runtime_id: str = ""
    run_id: str = ""
    storage_uri: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskPolicySummary(_ContractModel):
    """Phase 6C：风控策略版本 Registry 行。"""

    policy_hash: str
    policy_code: str
    policy_version: str
    engine_version: str = "qd_risk_engine@1"
    storage_uri: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskRunSummary(_ContractModel):
    """Phase 6C：幂等 risk evaluate 运行。"""

    risk_run_id: str
    idempotency_key: str
    policy_hash: str = ""
    account_id: str = ""
    portfolio_id: str = ""
    apply_id: str = ""
    trading_date: str = ""
    verdict: str = "ALLOW"
    n_intents: int = 0
    n_violations: int = 0
    storage_uri: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskDecisionEventRecord(_ContractModel):
    """Phase 6C：风控决策事件行。"""

    event_id: str
    risk_run_id: str
    rule_code: str = ""
    decision: str = ""
    severity: str = "P0"
    instrument_key: str = ""
    message: str = ""
    original_value: float = 0.0
    limit_value: float = 0.0
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class OmsOrderSummary(_ContractModel):
    """Phase 6D：OMS 订单 Registry 行。"""

    order_id: str
    client_order_id: str
    broker_order_id: str = ""
    account_id: str = ""
    portfolio_id: str = ""
    risk_run_id: str = ""
    policy_hash: str = ""
    instrument_key: str = ""
    side: str = "BUY"
    order_type: str = "MARKET"
    tif: str = "DAY"
    quantity: float = 0.0
    limit_price: Optional[float] = None
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    status: str = "CREATED"
    version: int = 1
    idempotency_key: str = ""
    trading_date: str = ""
    engine_version: str = "qd_oms@1"
    storage_uri: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OmsOrderEventRecord(_ContractModel):
    """Phase 6D：订单事件行。"""

    event_id: str
    order_id: str
    event_type: str
    previous_status: str = ""
    new_status: str = ""
    source: str = "OMS"
    message: str = ""
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class OmsFillSummary(_ContractModel):
    """Phase 6D：成交 Registry 行。"""

    fill_id: str
    order_id: str
    instrument_key: str = ""
    side: str = "BUY"
    quantity: float = 0.0
    price: float = 0.0
    fee: float = 0.0
    trading_date: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OmsOutboxRecord(_ContractModel):
    """Phase 6D：Outbox 行。"""

    outbox_id: str
    aggregate_type: str = "ORDER"
    aggregate_id: str = ""
    event_type: str = ""
    status: str = "PENDING"
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    sent_at: Optional[str] = None


class BrokerSessionSummary(_ContractModel):
    """Phase 6E：Broker 会话 Registry 行。"""

    session_id: str
    broker_id: str = ""
    execution_mode: str = "PAPER"
    status: str = "DISCONNECTED"
    engine_version: str = "qd_broker_adapter@1"
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrokerOrderLinkRecord(_ContractModel):
    """Phase 6E：order_id ↔ client_order_id ↔ broker_order_id。"""

    order_id: str
    client_order_id: str
    broker_order_id: str = ""
    broker_id: str = ""
    account_id: str = ""
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrokerEventIndexRecord(_ContractModel):
    """Phase 6E：Raw 事件索引（明细在 R2）。"""

    event_id: str
    broker_id: str = ""
    received_at: Optional[str] = None
    storage_uri: str = ""
    checksum: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReconciliationRunSummary(_ContractModel):
    """Phase 6F：对账运行 Registry 行。"""

    run_id: str
    account_id: str = ""
    portfolio_id: str = ""
    broker_id: str = ""
    mode: str = "FAST"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    snapshot_id: str = ""
    finding_count: int = 0
    critical_count: int = 0
    gate_blocked: bool = False
    engine_version: str = "qd_reconciliation@1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReconciliationFindingSummary(_ContractModel):
    """Phase 6F：Finding Registry 行。"""

    finding_id: str
    run_id: str = ""
    type: str = ""
    severity: str = "WARNING"
    status: str = "OPEN"
    entity_type: str = ""
    entity_id: str = ""
    expected: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any] = Field(default_factory=dict)
    difference: dict[str, Any] = Field(default_factory=dict)
    detected_at: Optional[str] = None
    resolved_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrokerSnapshotIndexRecord(_ContractModel):
    """Phase 6F：BrokerSnapshot 索引（明细在 R2）。"""

    snapshot_id: str
    broker_id: str = ""
    account_id: str = ""
    captured_at: Optional[str] = None
    storage_uri: str = ""
    checksum: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReconciliationCursorRecord(_ContractModel):
    """Phase 6F：增量游标。"""

    account_id: str
    broker_id: str = ""
    cursor_type: str = "EXECUTION"
    cursor_value: str = ""
    updated_at: Optional[str] = None


class ReconciliationGateRecord(_ContractModel):
    """Phase 6F：Trading Gate 状态。"""

    account_id: str
    blocked: bool = False
    reason: str = ""
    finding_id: str = ""
    updated_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyStateRecord(_ContractModel):
    """Phase 6G：按 scope 持久化的安全状态（热路径走 Registry）。"""

    scope: str
    scope_id: str
    state: str = "NORMAL"
    acknowledged: bool = False
    reason: str = ""
    updated_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyEventSummary(_ContractModel):
    """Phase 6G：SafetyEvent Registry 索引（明细在 R2）。"""

    event_id: str
    scope: str = "ACCOUNT"
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


class KillSwitchRecord(_ContractModel):
    """Phase 6G：Kill Switch 持久化行。"""

    scope: str
    scope_id: str
    engaged: bool = False
    reason: str = ""
    engaged_at: Optional[str] = None
    engaged_by: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyRuleRecord(_ContractModel):
    """Phase 6G：可配置规则 Registry 行。"""

    rule_id: str
    enabled: bool = True
    threshold: float = 0.0
    action: str = "BLOCK_NEW_ORDER"
    scope: str = "ACCOUNT"
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpsAuditEventSummary(_ContractModel):
    """Phase 6H：Audit Registry 索引（明细在 R2；只追加）。"""

    event_id: str
    event_type: str = ""
    timestamp: Optional[str] = None
    actor_type: str = "SYSTEM"
    actor_id: str = ""
    trace_id: str = ""
    account_id: str = ""
    strategy_id: str = ""
    order_id: str = ""
    entity_type: str = ""
    entity_id: str = ""
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpsHealthSnapshotRecord(_ContractModel):
    """Phase 6H：健康快照。"""

    snapshot_id: str
    captured_at: Optional[str] = None
    overall_status: str = "HEALTHY"
    health_json: dict[str, Any] = Field(default_factory=dict)
    counters_json: dict[str, Any] = Field(default_factory=dict)
    engine_version: str = "qd_ops@1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpsAlertRuleRecord(_ContractModel):
    """Phase 6H：告警规则。"""

    rule_id: str
    enabled: bool = True
    metric_or_signal: str = ""
    severity: str = "WARNING"
    threshold: float = 0.0
    comparison: str = "GT"
    description: str = ""
    safety_source_kind: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpsAlertEventSummary(_ContractModel):
    """Phase 6H：告警事件。"""

    alert_id: str
    rule_id: str = ""
    severity: str = "WARNING"
    fired_at: Optional[str] = None
    message: str = ""
    account_id: str = ""
    strategy_id: str = ""
    trace_id: str = ""
    incident_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpsIncidentSummary(_ContractModel):
    """Phase 6H：Incident 索引。"""

    incident_id: str
    title: str = ""
    severity: str = "WARNING"
    status: str = "OPEN"
    account_id: str = ""
    strategy_id: str = ""
    trace_id: str = ""
    opened_at: Optional[str] = None
    updated_at: Optional[str] = None
    resolved_at: Optional[str] = None
    timeline_event_ids: list[str] = Field(default_factory=list)
    alert_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpsSloDefinitionRecord(_ContractModel):
    """Phase 6H：SLO 配置。"""

    slo_id: str
    name: str = ""
    target_ratio: float = 0.999
    window_sec: float = 86400.0
    metric_name: str = ""
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class E2EScenarioRunSummary(_ContractModel):
    """Phase 6I：E2E 场景运行 Registry 索引（明细在 R2）。"""

    scenario_run_id: str
    scenario_id: str = ""
    run_id: str = ""
    session_id: str = ""
    mode: str = "PAPER"
    status: str = "OK"
    trace_id: str = ""
    dataset_hash: str = ""
    strategy_version: str = ""
    strategy_id: str = ""
    intent_fingerprint: str = ""
    engine_version: str = "qd_e2e@1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class E2ESessionSummary(_ContractModel):
    """Phase 6I：TradingSession 持久化行。"""

    session_id: str
    trading_date: str = ""
    market: str = ""
    mode: str = "PAPER"
    status: str = "OPEN"
    account_id: str = ""
    portfolio_id: str = ""
    dataset_hash: str = ""
    strategy_version: str = ""
    strategy_id: str = ""
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    engine_version: str = "qd_e2e@1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class E2EConsistencyScoreRecord(_ContractModel):
    """Phase 6I：ConsistencyScore Registry 索引。"""

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
    engine_version: str = "qd_e2e@1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class E2EVirtualOrderSummary(_ContractModel):
    """Phase 6I：Shadow 模式虚拟订单（不发 Broker）。"""

    virtual_order_id: str
    session_id: str = ""
    scenario_run_id: str = ""
    trace_id: str = ""
    instrument_key: str = ""
    side: str = "BUY"
    quantity: float = 0.0
    status: str = "WOULD_SUBMIT"
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
