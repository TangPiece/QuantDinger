"""CombinationFrames → 审计 R2 + 标准 Factor Dataset（4C 可读）。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

import pyarrow as pa

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import (
    FactorCombinationSummary,
    FactorDatasetRecord,
)
from app.services.research_data.factor_lab.artifact_store import (
    FactorDatasetArtifactStore,
)
from app.services.research_data.factor_lab.dataset import compute_factor_dataset_id
from app.services.research_data.factor_lab.models import FactorDatasetManifest
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data import writer as rd_writer

from .artifact_store import CombinationArtifactStore
from .protocol import (
    COMBINATION_VERSION,
    CombinationFrames,
    CombinationManifest,
    CombinationSpec,
)


class CombinationDatasetWriter:
    """双写：审计路径 + qd/factor/daily factor_set={composite_ref}。"""

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        artifact_store: CombinationArtifactStore | None = None,
        factor_artifact_store: FactorDatasetArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifact_store or CombinationArtifactStore()
        self._factor_arts = factor_artifact_store or FactorDatasetArtifactStore()

    def write(
        self,
        spec: CombinationSpec,
        frames: CombinationFrames,
        *,
        member_hashes: dict[str, str],
        snapshot_id: str = "",
        universe_code: str = "",
        force: bool = False,
        corr_summary: dict[str, Any] | None = None,
    ) -> FactorCombinationSummary:
        """写出 composite / corr / weights 并登记 Summary + FactorDataset。"""
        chash = frames.combination_hash
        if not force:
            try:
                return self._registry.get_factor_combination(chash)
            except (KeyError, AttributeError):
                pass

        checksums: list[str] = []
        checksums += self._write_composite_audit(spec, frames)
        if frames.corr_cells:
            written = rd_writer.write_factor_corr_matrix_panel(
                self._store,
                [
                    {
                        **c.model_dump(mode="json"),
                        "data_version": spec.combination_version,
                    }
                    for c in frames.corr_cells
                ],
                combination_hash=chash,
                version=spec.combination_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
        if frames.weights:
            written = rd_writer.write_combination_weights_panel(
                self._store,
                [
                    {
                        **w.model_dump(mode="json"),
                        "data_version": spec.combination_version,
                    }
                    for w in frames.weights
                ],
                combination_hash=chash,
                version=spec.combination_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])

        checksum = hashlib.sha256("".join(checksums or ["empty"]).encode()).hexdigest()

        composite_ref, composite_fid, _rec = self._register_factor_dataset(
            spec,
            frames,
            chash=chash,
            member_hashes=member_hashes,
            snapshot_id=snapshot_id,
            universe_code=universe_code,
        )

        weights_map = {w.factor_dataset_id: w.weight for w in frames.weights}
        summary = FactorCombinationSummary(
            combination_hash=chash,
            member_factor_dataset_ids_json=list(spec.member_factor_dataset_ids),
            normalize=spec.normalize,
            weight_method=spec.weight_method,
            weights_json=weights_map,
            correlation_summary_json=dict(corr_summary or {}),
            redundancy_pairs_json=[
                p.model_dump(mode="json") for p in frames.redundancy_pairs
            ],
            composite_factor_dataset_id=composite_fid,
            combination_version=spec.combination_version or COMBINATION_VERSION,
            metadata={
                "composite_factor_ref": composite_ref,
                "member_hashes": dict(member_hashes),
                "orthogonalized": spec.weight_method == "ORTHOGONALIZE",
            },
        )

        man = CombinationManifest(
            combination_hash=chash,
            member_factor_dataset_ids=list(spec.member_factor_dataset_ids),
            composite_factor_dataset_id=composite_fid,
            composite_factor_ref=composite_ref,
            combination_spec=spec.model_dump(mode="json"),
            composite_rows=len(frames.composite_rows),
            checksum=checksum,
            combination_version=spec.combination_version,
            metadata={"member_hashes": dict(member_hashes)},
        )
        art = self._artifacts.write_manifest(man, summary=summary)
        summary = summary.model_copy(
            update={"storage_uri": art.storage_uri, "checksum": art.checksum}
        )
        self._registry.upsert_factor_combination(summary)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return summary

    def _write_composite_audit(
        self, spec: CombinationSpec, frames: CombinationFrames
    ) -> list[str]:
        """按年月写审计 composite 分区（含成员列）。"""
        by_ym: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for r in frames.composite_rows:
            row: dict[str, Any] = {
                "instrument_key": r.instrument_key,
                "trading_date": r.trading_date,
                "composite": float(r.composite),
                "combination_hash": frames.combination_hash,
                "data_version": spec.combination_version,
            }
            # 审计保留成员值（原名 mid 可能过长，用短前缀）
            for mid, val in (r.member_values or {}).items():
                safe = f"m_{mid[:24]}"
                row[safe] = float(val)
            by_ym[(r.trading_date.year, r.trading_date.month)].append(row)

        checksums: list[str] = []
        for (y, m), part in sorted(by_ym.items()):
            written = rd_writer.write_composite_factor_panel(
                self._store,
                part,
                combination_hash=frames.combination_hash,
                year=y,
                month=m,
                version=spec.combination_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
        return checksums

    def _register_factor_dataset(
        self,
        spec: CombinationSpec,
        frames: CombinationFrames,
        *,
        chash: str,
        member_hashes: dict[str, str],
        snapshot_id: str,
        universe_code: str,
    ) -> tuple[str, str, FactorDatasetRecord]:
        """写出标准 long factor parquet 并登记 FactorDatasetRecord。"""
        code = "composite"
        version = f"c_{chash[:12]}"
        composite_ref = f"{code}@{version}"

        dataset_hash = hashlib.sha256(
            f"{chash}:{':'.join(sorted(member_hashes.values()))}".encode()
        ).hexdigest()
        dates = sorted({r.trading_date for r in frames.composite_rows})
        start = dates[0].isoformat() if dates else ""
        end = dates[-1].isoformat() if dates else ""
        fid = compute_factor_dataset_id(
            factor_hash=chash,
            dataset_hash=dataset_hash,
            snapshot_id=snapshot_id or f"comb_{chash[:8]}",
            universe_code=universe_code,
            frequency="1d",
            start_date=start,
            end_date=end,
            layout="long",
        )

        by_ym: dict[tuple[int, int], list] = defaultdict(list)
        for r in frames.composite_rows:
            by_ym[(r.trading_date.year, r.trading_date.month)].append(
                {
                    "instrument_key": r.instrument_key,
                    "trading_date": r.trading_date,
                    "factor_code": code,
                    "factor_version": version,
                    "value": float(r.composite),
                    "data_version": spec.combination_version,
                }
            )
        checksums = []
        total = 0
        for (y, m), part in sorted(by_ym.items()):
            table = pa.Table.from_pylist(part)
            written = rd_writer.write_factor_long(
                self._store,
                table,
                factor_set=composite_ref,
                year=y,
                month=m,
                version=spec.combination_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
            total += int(written["row_count"])
        fac_checksum = hashlib.sha256(
            "".join(checksums or ["empty"]).encode()
        ).hexdigest()

        rec = FactorDatasetRecord(
            factor_dataset_id=fid,
            factor_ref=composite_ref,
            factor_hash=chash,
            dataset_hash=dataset_hash,
            snapshot_id=snapshot_id or f"comb_{chash[:8]}",
            universe_code=universe_code,
            frequency="1d",
            start_date=start,
            end_date=end,
            storage_uri=f"factor_set={composite_ref}",
            checksum=fac_checksum,
            row_count=total,
            layout="long",
            schema_version="factor_daily_long@1",
            status="ACTIVE",
            metadata={
                "combination_hash": chash,
                "member_factor_dataset_ids": list(spec.member_factor_dataset_ids),
                "normalize": spec.normalize,
                "weight_method": spec.weight_method,
            },
        )
        self._registry.upsert_factor_dataset(rec)
        man = FactorDatasetManifest(
            factor_code=code,
            factor_version=version,
            factor_hash=chash,
            dataset_hash=dataset_hash,
            snapshot_id=rec.snapshot_id,
            schema_version="factor_daily_long@1",
            min_date=start,
            max_date=end,
            universe=universe_code,
            row_count=total,
            checksum=fac_checksum,
            layout="long",
            engine="combination",
            engine_version=spec.combination_version,
            factor_dataset_id=fid,
            frequency="1d",
            storage_uri=rec.storage_uri,
            metadata=dict(rec.metadata or {}),
        )
        self._factor_arts.write_manifest(man, record=rec)
        return composite_ref, fid, rec
