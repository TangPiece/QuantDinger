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
