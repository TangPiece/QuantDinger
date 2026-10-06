"""FactorFrame → Parquet + Manifest + Registry（不可覆盖旧 Dataset）。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

import pyarrow as pa

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import FactorDatasetRecord, FeatureDefinition
from app.services.research_data.factor_lab.artifact_store import FactorDatasetArtifactStore
from app.services.research_data.factor_lab.dataset import (
    build_factor_dataset_record,
    build_manifest,
    compute_factor_dataset_id,
)
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data import schemas, writer as rd_writer

from .hash import compute_result_dataset_hash
from .protocol import ComputePlan, FactorFrame


class FactorDatasetWriter:
    """将 FactorFrame 按月分区写入，并登记 FactorDataset。"""

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        artifact_store: FactorDatasetArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifact_store or FactorDatasetArtifactStore()

    def write(
        self,
        feature: FeatureDefinition,
        plan: ComputePlan,
        frame: FactorFrame,
    ) -> FactorDatasetRecord:
        """写出 parquet + manifest；同 factor_dataset_id 已存在则幂等返回。"""
        result_hash = compute_result_dataset_hash(plan)
        fid = compute_factor_dataset_id(
            factor_hash=plan.factor_hash,
            dataset_hash=result_hash,
            snapshot_id=plan.snapshot_id,
            universe_code=plan.universe_code,
            frequency=plan.frequency,
            start_date=plan.start_date,
            end_date=plan.end_date,
            layout=plan.layout,
        )
        try:
            existing = self._registry.get_factor_dataset(fid)
            return existing
        except KeyError:
            pass

        checksums: list[str] = []
        total_rows = 0
        uris: list[str] = []
        if frame.layout == "wide":
            written = self._write_wide(feature, plan, frame)
        else:
            written = self._write_long(feature, plan, frame)
        for item in written:
            checksums.append(item["checksum"])
            total_rows += int(item["row_count"])
            uris.append(item.get("r2_uri") or item.get("key") or "")

        # 聚合 checksum
        import hashlib

        checksum = hashlib.sha256("".join(checksums).encode("utf-8")).hexdigest()
        storage_uri = uris[0] if len(uris) == 1 else f"multi:{len(uris)}"

        record = build_factor_dataset_record(
            feature,
            dataset_hash=result_hash,
            snapshot_id=plan.snapshot_id,
            start_date=plan.start_date,
            end_date=plan.end_date,
            universe_code=plan.universe_code,
            layout=plan.layout,
            storage_uri=storage_uri,
            checksum=checksum,
            row_count=total_rows,
        )
        # 确保 id 与 result_hash 一致
        record = record.model_copy(
            update={"factor_dataset_id": fid, "dataset_hash": result_hash}
        )
        man = build_manifest(
            feature,
            record,
            checksum=checksum,
            row_count=total_rows,
            min_date=frame.min_date or plan.start_date,
            max_date=frame.max_date or plan.end_date,
            metadata={
                "engine": plan.engine,
                "engine_version": plan.engine_version,
                "plan_hash": plan.plan_hash,
                "parts": len(written),
            },
        )
        man = man.model_copy(
            update={
                "engine": plan.engine,
                "engine_version": plan.engine_version,
                "factor_dataset_id": fid,
            }
        )
        art = self._artifacts.write_manifest(man, record=record)
        record = record.model_copy(
            update={"storage_uri": art.storage_uri, "checksum": art.checksum}
        )
        self._registry.upsert_factor_dataset(record)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return record

    def _write_long(
        self, feature: FeatureDefinition, plan: ComputePlan, frame: FactorFrame
    ) -> list[dict[str, Any]]:
        by_ym: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for r in frame.records:
            day = str(r["trading_date"])[:10]
            y, m = int(day[:4]), int(day[5:7])
            by_ym[(y, m)].append(r)
        factor_set = f"{feature.code}@{feature.version}"
        out = []
        for (y, m), rows in sorted(by_ym.items()):
            table = pa.Table.from_pylist(
                [
                    {
                        "instrument_key": r["instrument_key"],
                        "trading_date": date.fromisoformat(str(r["trading_date"])[:10]),
                        "factor_code": feature.code,
                        "factor_version": feature.version,
                        "value": float(r["value"]),
                        "data_version": plan.factor_hash[:16],
                    }
                    for r in rows
                ]
            )
            out.append(
                rd_writer.write_factor_long(
                    self._store,
                    table,
                    factor_set=factor_set,
                    year=y,
                    month=m,
                    version=feature.version,
                    registry=self._registry,
                )
            )
        return out

    def _write_wide(
        self, feature: FeatureDefinition, plan: ComputePlan, frame: FactorFrame
    ) -> list[dict[str, Any]]:
        by_ym: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for r in frame.records:
            day = str(r["trading_date"])[:10]
            y, m = int(day[:4]), int(day[5:7])
            by_ym[(y, m)].append(r)
        factor_set = f"{feature.code}@{feature.version}"
        cols = frame.factor_columns or [feature.code]
        out = []
        for (y, m), rows in sorted(by_ym.items()):
            out.append(
                rd_writer.write_factor_wide(
                    self._store,
                    rows,
                    factor_set=factor_set,
                    year=y,
                    month=m,
                    version=feature.version,
                    factor_columns=cols,
                    registry=self._registry,
                )
            )
        return out
