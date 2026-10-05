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
    code: str
    version: str
    name: str
    expression: str
    frequency: str = "1d"
    dependencies: list[str] = Field(default_factory=list)
    backend: Literal["r2_factor", "d1_l2_factors", "computed"] = "r2_factor"
    online_supported: bool = False
    definition: dict[str, Any] = Field(default_factory=dict)


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


class ModelArtifact(_ContractModel):
    model_code: str
    version: str
    engine: str
    dataset_ref: str
    processor_ref: Optional[str] = None
    artifact_uri: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class ExperimentDefinition(_ContractModel):
    experiment_id: str
    name: str
    dataset_ref: str
    snapshot_id: str
    dataset_hash: str
    model_version_ref: Optional[str] = None
    mlflow_run_id: Optional[str] = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class Signal(_ContractModel):
    instrument_key: str
    timestamp: datetime
    score: float
    rank: Optional[int] = None
    confidence: Optional[float] = None
    model_version: Optional[str] = None


class TargetPosition(_ContractModel):
    instrument_key: str
    timestamp: datetime
    target_weight: Optional[float] = None
    target_quantity: Optional[float] = None


class OrderIntent(_ContractModel):
    instrument_key: str
    side: Literal["BUY", "SELL"]
    quantity: float
    urgency: Literal["LOW", "NORMAL", "HIGH"] = "NORMAL"
    execution_algorithm: Literal["MARKET", "LIMIT", "TWAP", "VWAP", "POV", "CUSTOM"] = "MARKET"
    limit_price: Optional[float] = None
