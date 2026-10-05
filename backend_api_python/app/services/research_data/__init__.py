"""研究数据地基：Domain Contract、Canonical Store、DataQuery。

所有研究读路径必须经 DataQuery；禁止直连实时行情 API。
契约见 docs/data/phase1/。
"""

from .contracts import (
    DataVersionRef,
    DatasetDefinition,
    DatasetHandle,
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
from .canonical_repository import CanonicalRepository
from .data_query import DataQuery
from .hashing import compute_dataset_hash

__all__ = [
    "CanonicalRepository",
    "DataQuery",
    "DataVersionRef",
    "DatasetDefinition",
    "DatasetHandle",
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
