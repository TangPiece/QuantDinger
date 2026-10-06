"""FactorMetricsService：Evaluation Dataset → IC/RankIC → Summary。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import (
    EvaluationDatasetRecord,
    FactorEvaluationSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .aggregator import ICStatisticsAggregator
from .artifact_store import MetricArtifactStore
from .calculators import CrossSectionalICEngine
from .hash import compute_metric_hash
from .protocol import MetricSpec, MetricTimeSeries
from .writers import MetricDatasetWriter


class FactorMetricsError(RuntimeError):
    """指标计算失败。"""


@dataclass
class MetricsResult:
    """指标运行结果。"""

    metric_hash: str
    timeseries: MetricTimeSeries
    summaries: list[FactorEvaluationSummary]
    evaluation: EvaluationDatasetRecord | None = None


class FactorMetricsService:
    """只消费 4C Evaluation Dataset；不重算 Forward Return / PIT / Universe。"""

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        artifact_store: MetricArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifact_store or MetricArtifactStore()
        self._engine = CrossSectionalICEngine()
        self._agg = ICStatisticsAggregator()
        self._writer = MetricDatasetWriter(
            store, registry, artifact_store=self._artifacts
        )

    def run(
        self,
        evaluation_hash: str,
        spec: MetricSpec | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> MetricsResult:
        """端到端：load panel → IC/RankIC → aggregate → persist。"""
        meta = dict(metadata or {})
        try:
            eval_rec = self._registry.get_evaluation_dataset(evaluation_hash)
        except KeyError as exc:
            if meta.get("evaluation_records") is None:
                raise FactorMetricsError(
                    f"evaluation_dataset not found: {evaluation_hash}"
                ) from exc
            eval_rec = None

        mspec = spec or MetricSpec(evaluation_hash=evaluation_hash)
        if mspec.evaluation_hash != evaluation_hash:
            mspec = mspec.model_copy(update={"evaluation_hash": evaluation_hash})

        mhash = compute_metric_hash(mspec)
        force = bool(meta.get("force_recompute"))

        if not force:
            try:
                # 幂等：已有 summary 则直接返回（测试可注入 records 强制重算）
                if meta.get("evaluation_records") is None and eval_rec is not None:
                    horizons = mspec.horizons or [1]
                    summaries = [
                        self._registry.get_factor_evaluation_summary(mhash, h)
                        for h in horizons
                    ]
                    return MetricsResult(
                        metric_hash=mhash,
                        timeseries=MetricTimeSeries(
                            metric_hash=mhash,
                            evaluation_hash=evaluation_hash,
                            horizons=list(horizons),
                        ),
                        summaries=summaries,
                        evaluation=eval_rec,
                    )
            except KeyError:
                pass

        records = self._load_records(evaluation_hash, eval_rec, meta)
        series = self._engine.calculate(records, mspec, metric_hash=mhash)
        # 若 horizons 为 None，用推断结果写回 hash 一致性：hash 已按 None 计算，OK
        factor_ds_id = (
            (eval_rec.factor_dataset_id if eval_rec else "")
            or str(meta.get("factor_dataset_id") or "")
        )
        summaries = self._agg.aggregate(
            series, mspec, factor_dataset_id=factor_ds_id
        )
        written = self._writer.write(
            mspec,
            series,
            summaries,
            factor_dataset_id=factor_ds_id,
            force=force,
        )
        return MetricsResult(
            metric_hash=mhash,
            timeseries=series,
            summaries=written,
            evaluation=eval_rec,
        )

    def _load_records(
        self,
        evaluation_hash: str,
        eval_rec: EvaluationDatasetRecord | None,
        meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """优先 metadata 注入；否则读 evaluation parquet。"""
        if meta.get("evaluation_records") is not None:
            return list(meta["evaluation_records"])
        from app.services.research_data import config as rd_config
        from app.services.research_data.canonical_repository import CanonicalRepository

        prefix = (
            f"{rd_config.canonical_prefix()}/evaluation/factor/{evaluation_hash}"
        )
        try:
            df = CanonicalRepository(self._store).read_parquet_df(prefix=prefix)
        except Exception as exc:
            raise FactorMetricsError(
                f"failed to load evaluation panel for {evaluation_hash}; "
                "pass metadata['evaluation_records'] in tests"
            ) from exc
        if df is None or df.empty:
            raise FactorMetricsError(f"empty evaluation panel: {evaluation_hash}")
        return df.to_dict(orient="records")
