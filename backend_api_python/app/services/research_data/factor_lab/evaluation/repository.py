"""Evaluation Repository Protocols（Domain 不依赖 R2 SDK / DuckDB / Polars / Qlib）。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.services.research_data.contracts import EvaluationDatasetRecord

from .protocol import EvaluationManifest


@runtime_checkable
class EvaluationDatasetRepository(Protocol):
    """评价数据集 Registry 读写。"""

    def upsert_evaluation_dataset(self, record: EvaluationDatasetRecord) -> None: ...

    def get_evaluation_dataset(self, evaluation_hash: str) -> EvaluationDatasetRecord: ...


@runtime_checkable
class EvaluationManifestRepository(Protocol):
    """Manifest 落盘抽象。"""

    def write_manifest(self, manifest: EvaluationManifest) -> str: ...

    def read_manifest(self, evaluation_hash: str) -> EvaluationManifest: ...


@runtime_checkable
class ForwardReturnRepository(Protocol):
    """远期收益中间结果（可选缓存；4C 默认可空实现）。"""

    def put(self, key: str, payload: dict) -> None: ...

    def get(self, key: str) -> dict: ...


@runtime_checkable
class EvaluationRepository(Protocol):
    """组合入口。"""

    datasets: EvaluationDatasetRepository
    manifests: EvaluationManifestRepository
