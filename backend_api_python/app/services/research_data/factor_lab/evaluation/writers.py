"""EvaluationFrame → Parquet + Manifest + Registry（不可覆盖旧评价集）。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import EvaluationDatasetRecord
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data import writer as rd_writer

from .artifact_store import EvaluationArtifactStore
from .protocol import (
    SCHEMA_EVALUATION,
    EvaluationFrame,
    EvaluationManifest,
    EvaluationPlan,
)


class EvaluationDatasetWriter:
    """将评价面板按月分区写入并登记。"""

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        artifact_store: EvaluationArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifact_store or EvaluationArtifactStore()

    def write(
        self,
        plan: EvaluationPlan,
        frame: EvaluationFrame,
        *,
        force: bool = False,
    ) -> EvaluationDatasetRecord:
        """写出 parquet + manifest；同 evaluation_hash 已存在则幂等返回。"""
        ehash = plan.evaluation_hash
        if not force:
            try:
                existing = self._registry.get_evaluation_dataset(ehash)
                return existing
            except KeyError:
                pass
            except AttributeError:
                pass

        by_ym: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for r in frame.records:
            day = str(r["factor_date"])[:10]
            y, m = int(day[:4]), int(day[5:7])
            by_ym[(y, m)].append(r)

        written: list[dict[str, Any]] = []
        for (y, m), rows in sorted(by_ym.items()):
            written.append(
                rd_writer.write_evaluation_panel(
                    self._store,
                    rows,
                    evaluation_hash=ehash,
                    year=y,
                    month=m,
                    horizons=frame.horizons or list(plan.return_spec.horizons),
                    version=plan.evaluator_version,
                    registry=self._registry,
                )
            )

        checksums = [w["checksum"] for w in written]
        total_rows = sum(int(w["row_count"]) for w in written)
        checksum = hashlib.sha256("".join(checksums).encode("utf-8")).hexdigest()
        record = EvaluationDatasetRecord(
            evaluation_hash=ehash,
            factor_dataset_id=plan.factor_dataset_id,
            factor_dataset_hash=plan.factor_dataset_hash,
            snapshot_id=plan.snapshot_id,
            universe_code=plan.universe_code,
            universe_version=plan.universe_version,
            start_date=plan.start_date,
            end_date=plan.end_date,
            return_spec=plan.return_spec.model_dump(mode="json"),
            price_policy=plan.price_policy,
            evaluator_version=plan.evaluator_version,
            mode=plan.mode,
            storage_uri="",
            checksum=checksum,
            row_count=total_rows,
            schema_version=SCHEMA_EVALUATION,
            metadata={"parts": len(written)},
        )
        man = EvaluationManifest(
            evaluation_hash=ehash,
            factor_dataset_id=plan.factor_dataset_id,
            factor_dataset_hash=plan.factor_dataset_hash,
            evaluation_spec={
                "universe_code": plan.universe_code,
                "universe_version": plan.universe_version,
                "snapshot_id": plan.snapshot_id,
                "start_date": plan.start_date,
                "end_date": plan.end_date,
                "mode": plan.mode,
                "calendar_version": plan.calendar_version,
            },
            return_spec=plan.return_spec.model_dump(mode="json"),
            universe_code=plan.universe_code,
            universe_version=plan.universe_version,
            snapshot_id=plan.snapshot_id,
            row_count=total_rows,
            min_date=frame.min_date or plan.start_date,
            max_date=frame.max_date or plan.end_date,
            checksum=checksum,
            evaluator_version=plan.evaluator_version,
            schema_version=SCHEMA_EVALUATION,
            mode=plan.mode,
            metadata={"parts": len(written)},
        )
        art = self._artifacts.write_manifest(man, record=record)
        record = record.model_copy(
            update={"storage_uri": art.storage_uri, "checksum": art.checksum}
        )
        self._registry.upsert_evaluation_dataset(record)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return record
