"""研究数据地基：Domain Contract、Canonical Store、DataQuery。

所有研究读路径必须经 DataQuery；禁止直连实时行情 API。
契约见 docs/data/phase1/。
"""

from .contracts import (
    ConsistencyRunRecord,
    DataVersionRef,
    DatasetDefinition,
    DatasetHandle,
    FactorDatasetRecord,
    FeatureDefinition,
    InstrumentKey,
    LabelDefinition,
    OrderIntent,
    PredictionRecord,
    PricePolicy,
    ProcessorDefinition,
    Signal,
    SignalRunRecord,
    SnapshotRef,
    TargetPosition,
)
from .hashing import compute_dataset_hash

# CanonicalRepository / DataQuery pull duckdb — lazy so product Flask boot
# does not require duckdb until a research read path actually uses them.
def __getattr__(name: str):
    if name == "CanonicalRepository":
        from .canonical_repository import CanonicalRepository

        return CanonicalRepository
    if name == "DataQuery":
        from .data_query import DataQuery

        return DataQuery
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CanonicalRepository",
    "ConsistencyRunRecord",
    "DataQuery",
    "DataVersionRef",
    "DatasetDefinition",
    "DatasetHandle",
    "FactorDatasetRecord",
    "FeatureDefinition",
    "InstrumentKey",
    "LabelDefinition",
    "OrderIntent",
    "PredictionRecord",
    "PricePolicy",
    "ProcessorDefinition",
    "Signal",
    "SignalRunRecord",
    "SnapshotRef",
    "TargetPosition",
    "compute_dataset_hash",
]
