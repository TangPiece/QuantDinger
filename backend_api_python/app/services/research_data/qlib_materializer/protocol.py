"""Materializer 契约：结果对象与状态枚举。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class MaterializationStatus(str, Enum):
    """派生缓存生命周期状态。"""

    BUILDING = "BUILDING"
    READY = "READY"
    FAILED = "FAILED"
    INVALID = "INVALID"


class MaterializationResult(BaseModel):
    """一次物化的对外结果（含 cache hit）。"""

    model_config = ConfigDict(extra="forbid")

    dataset_hash: str
    materialization_id: str
    cache_path: str
    manifest_path: str
    status: MaterializationStatus
    created_at: datetime
    row_count: int = 0
    instrument_count: int = 0
    calendar_count: int = 0
    feature_count: int = 0
    checksum: str = ""
    cache_hit: bool = False
    qlib_version: str = ""
    materializer_version: str = ""
    notes: list[str] = Field(default_factory=list)


class QlibMaterializer(Protocol):
    """Dataset → Qlib Cache 物化协议。"""

    def materialize(self, dataset_ref: str, *, force: bool = False) -> MaterializationResult:
        """物化指定 Dataset（`code@version`）；force 时忽略 cache hit。"""
        ...
