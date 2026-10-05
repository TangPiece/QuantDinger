"""Qlib Materializer：Dataset/DataQuery → 本地 Qlib 派生缓存（非 SSOT）。

硬约束：只读 DataQuery；禁止 Source / PG / R2 SDK / HTTP API。
"""

from .identity import MATERIALIZER_VERSION, compute_materialization_id
from .protocol import MaterializationResult, MaterializationStatus
from .qlib_materializer import DefaultQlibMaterializer

__all__ = [
    "MATERIALIZER_VERSION",
    "DefaultQlibMaterializer",
    "MaterializationResult",
    "MaterializationStatus",
    "compute_materialization_id",
]
