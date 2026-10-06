"""MetricTimeSeries → Parquet + summary/manifest + Registry。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import FactorEvaluationSummary
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data import writer as rd_writer

from .artifact_store import MetricArtifactStore
from .protocol import (
    SCHEMA_METRIC_IC,
    MetricManifest,
    MetricSpec,
    MetricTimeSeries,
    point_date_str,
)


class MetricDatasetWriter:
    """写出 IC 时间序列与 Summary；同 metric_hash 幂等。"""

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

    def write(
        self,
        spec: MetricSpec,
        series: MetricTimeSeries,
        summaries: list[FactorEvaluationSummary],
        *,
        factor_dataset_id: str = "",
        force: bool = False,
    ) -> list[FactorEvaluationSummary]:
        """写 parquet + manifest；返回已登记 summaries。"""
        mhash = series.metric_hash
        if not force:
            try:
                existing = self._registry.get_factor_evaluation_summary(mhash, summaries[0].horizon)
                # 若已有任一 horizon，整组视为已写
                if existing.metric_hash == mhash:
                    out = []
                    for s in summaries:
                        try:
                            out.append(
                                self._registry.get_factor_evaluation_summary(
                                    mhash, s.horizon
                                )
                            )
                        except KeyError:
                            out.append(s)
                    return out
            except (KeyError, IndexError, AttributeError):
                pass

        by_ym: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for p in series.points:
            day = point_date_str(p.evaluation_date)
            y, m = int(day[:4]), int(day[5:7])
            by_ym[(y, m)].append(
                {
                    "evaluation_date": p.evaluation_date,
                    "horizon": p.horizon,
                    "ic": p.ic,
                    "rank_ic": p.rank_ic,
                    "sample_count": p.sample_count,
                    "valid": p.valid,
                }
            )

        written: list[dict[str, Any]] = []
        for (y, m), rows in sorted(by_ym.items()):
            written.append(
                rd_writer.write_metric_ic_panel(
                    self._store,
                    rows,
                    metric_hash=mhash,
                    year=y,
                    month=m,
                    version=spec.metric_version,
                    registry=self._registry,
                )
            )

        checksums = [w["checksum"] for w in written] if written else ["empty"]
        checksum = hashlib.sha256("".join(checksums).encode("utf-8")).hexdigest()
        dates = [point_date_str(p.evaluation_date) for p in series.points]
        man = MetricManifest(
            metric_hash=mhash,
            evaluation_hash=spec.evaluation_hash,
            factor_dataset_id=factor_dataset_id,
            metric_spec=spec.model_dump(mode="json"),
            horizons=list(series.horizons),
            row_count=series.row_count,
            min_date=min(dates) if dates else "",
            max_date=max(dates) if dates else "",
            checksum=checksum,
            metric_version=spec.metric_version,
            calculator_version=spec.calculator_version,
            schema_version=SCHEMA_METRIC_IC,
            metadata={"parts": len(written)},
        )
        art = self._artifacts.write_manifest(man, summaries=summaries)
        out: list[FactorEvaluationSummary] = []
        for s in summaries:
            rec = s.model_copy(
                update={
                    "storage_uri": art.storage_uri,
                    "checksum": art.checksum,
                    "factor_dataset_id": factor_dataset_id or s.factor_dataset_id,
                }
            )
            self._registry.upsert_factor_evaluation_summary(rec)
            out.append(rec)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return out
