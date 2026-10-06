"""Metric Repository Protocols（Domain 无 R2/D1/Polars/DuckDB/Qlib SDK）。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.services.research_data.contracts import FactorEvaluationSummary

from .protocol import MetricManifest, MetricTimeSeries


@runtime_checkable
class MetricTimeSeriesRepository(Protocol):
    def put(self, series: MetricTimeSeries) -> None: ...

    def get(self, metric_hash: str) -> MetricTimeSeries: ...


@runtime_checkable
class FactorEvaluationSummaryRepository(Protocol):
    def upsert_factor_evaluation_summary(
        self, record: FactorEvaluationSummary
    ) -> None: ...

    def get_factor_evaluation_summary(
        self, metric_hash: str, horizon: int
    ) -> FactorEvaluationSummary: ...


@runtime_checkable
class MetricManifestRepository(Protocol):
    def write_manifest(self, manifest: MetricManifest) -> str: ...

    def read_manifest(self, metric_hash: str) -> MetricManifest: ...
