"""NeutralizationFrames → 审计 R2 + 标准 Factor Dataset（4C 可读）。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

import pyarrow as pa

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import (
    FactorDatasetRecord,
    FactorNeutralizationSummary,
)
from app.services.research_data.factor_lab.artifact_store import (
    FactorDatasetArtifactStore,
)
from app.services.research_data.factor_lab.dataset import compute_factor_dataset_id
from app.services.research_data.factor_lab.models import FactorDatasetManifest
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data import writer as rd_writer

from .artifact_store import NeutralizationArtifactStore
from .diagnostics import ExposureDiagnosticCalculator
from .protocol import (
    NEUTRALIZATION_VERSION,
    NeutralizationFrames,
    NeutralizationManifest,
    NeutralizationSpec,
)


class NeutralizationDatasetWriter:
    """双写：审计路径 + qd/factor/daily factor_set={neut_ref}。"""

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        artifact_store: NeutralizationArtifactStore | None = None,
        factor_artifact_store: FactorDatasetArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifact_store or NeutralizationArtifactStore()
        self._factor_arts = factor_artifact_store or FactorDatasetArtifactStore()
        self._diag_agg = ExposureDiagnosticCalculator()

    def write(
        self,
        spec: NeutralizationSpec,
        frames: NeutralizationFrames,
        *,
        factor_dataset_hash: str,
        raw_factor_ref: str,
        snapshot_id: str = "",
        universe_code: str = "",
        force: bool = False,
    ) -> FactorNeutralizationSummary:
        nhash = frames.neutralization_hash
        if not force:
            try:
                return self._registry.get_factor_neutralization(nhash)
            except (KeyError, AttributeError):
                pass

        checksums: list[str] = []
        # 审计 factor
        checksums += self._write_dated(
            nhash,
            "factor",
            [
                {
                    **r.model_dump(mode="json"),
                    "neutralization_hash": nhash,
                }
                for r in frames.factor_rows
            ],
            spec.neutralization_version,
            rd_writer.write_neutralized_factor_panel,
        )
        checksums += self._write_dated(
            nhash,
            "exposure",
            [e.model_dump(mode="json") for e in frames.exposure_rows],
            spec.neutralization_version,
            rd_writer.write_exposure_panel,
        )
        if frames.diagnostics:
            written = rd_writer.write_neutralization_diagnostics_panel(
                self._store,
                [d.model_dump(mode="json") for d in frames.diagnostics],
                neutralization_hash=nhash,
                version=spec.neutralization_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])

        checksum = hashlib.sha256("".join(checksums or ["empty"]).encode()).hexdigest()

        # 标准 Factor Dataset（4C）
        neut_ref, neut_fid, neut_rec = self._register_factor_dataset(
            spec,
            frames,
            nhash=nhash,
            factor_dataset_hash=factor_dataset_hash,
            raw_factor_ref=raw_factor_ref,
            snapshot_id=snapshot_id,
            universe_code=universe_code,
        )

        diag_summary = self._diag_agg.summarize(frames.diagnostics)
        summary = FactorNeutralizationSummary(
            neutralization_hash=nhash,
            factor_dataset_id=spec.factor_dataset_id,
            factor_dataset_hash=factor_dataset_hash,
            method=spec.method,
            targets_json=list(spec.targets),
            r_squared_mean=diag_summary.get("r_squared_mean"),
            diagnostics_json=diag_summary,
            neutralized_factor_dataset_id=neut_fid,
            neutralization_version=spec.neutralization_version
            or NEUTRALIZATION_VERSION,
            metadata={
                "neut_factor_ref": neut_ref,
                "raw_factor_ref": raw_factor_ref,
            },
        )

        man = NeutralizationManifest(
            neutralization_hash=nhash,
            factor_dataset_id=spec.factor_dataset_id,
            factor_dataset_hash=factor_dataset_hash,
            neutralized_factor_dataset_id=neut_fid,
            neut_factor_ref=neut_ref,
            neutralization_spec=spec.model_dump(mode="json"),
            factor_rows=len(frames.factor_rows),
            exposure_rows=len(frames.exposure_rows),
            diagnostic_rows=len(frames.diagnostics),
            checksum=checksum,
            neutralization_version=spec.neutralization_version,
        )
        art = self._artifacts.write_manifest(man, summary=summary)
        summary = summary.model_copy(
            update={"storage_uri": art.storage_uri, "checksum": art.checksum}
        )
        self._registry.upsert_factor_neutralization(summary)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return summary

    def _register_factor_dataset(
        self,
        spec: NeutralizationSpec,
        frames: NeutralizationFrames,
        *,
        nhash: str,
        factor_dataset_hash: str,
        raw_factor_ref: str,
        snapshot_id: str,
        universe_code: str,
    ) -> tuple[str, str, FactorDatasetRecord]:
        """写出标准 long factor parquet 并登记 FactorDatasetRecord。"""
        code = "neut_factor"
        version = f"n_{nhash[:12]}"
        neut_ref = f"{code}@{version}"
        # 禁止撞 raw 路径
        if neut_ref == raw_factor_ref:
            version = f"n_{nhash[:16]}"
            neut_ref = f"{code}@{version}"

        dataset_hash = hashlib.sha256(
            f"{factor_dataset_hash}:{nhash}".encode()
        ).hexdigest()
        dates = sorted({r.trading_date for r in frames.factor_rows})
        start = dates[0].isoformat() if dates else ""
        end = dates[-1].isoformat() if dates else ""
        fid = compute_factor_dataset_id(
            factor_hash=nhash,
            dataset_hash=dataset_hash,
            snapshot_id=snapshot_id or f"neut_{nhash[:8]}",
            universe_code=universe_code,
            frequency="1d",
            start_date=start,
            end_date=end,
            layout="long",
        )

        by_ym: dict[tuple[int, int], list] = defaultdict(list)
        for r in frames.factor_rows:
            if r.neutralized_factor is None:
                continue
            by_ym[(r.trading_date.year, r.trading_date.month)].append(
                {
                    "instrument_key": r.instrument_key,
                    "trading_date": r.trading_date,
                    "factor_code": code,
                    "factor_version": version,
                    "value": float(r.neutralized_factor),
                    "data_version": spec.neutralization_version,
                }
            )
        checksums = []
        total = 0
        for (y, m), part in sorted(by_ym.items()):
            table = pa.Table.from_pylist(part)
            written = rd_writer.write_factor_long(
                self._store,
                table,
                factor_set=neut_ref,
                year=y,
                month=m,
                version=spec.neutralization_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
            total += int(written["row_count"])
        fac_checksum = hashlib.sha256(
            "".join(checksums or ["empty"]).encode()
        ).hexdigest()

        rec = FactorDatasetRecord(
            factor_dataset_id=fid,
            factor_ref=neut_ref,
            factor_hash=nhash,
            dataset_hash=dataset_hash,
            snapshot_id=snapshot_id or f"neut_{nhash[:8]}",
            universe_code=universe_code,
            frequency="1d",
            start_date=start,
            end_date=end,
            storage_uri=f"factor_set={neut_ref}",
            checksum=fac_checksum,
            row_count=total,
            layout="long",
            schema_version="factor_daily_long@1",
            status="ACTIVE",
            metadata={
                "neutralization_hash": nhash,
                "raw_factor_dataset_id": spec.factor_dataset_id,
                "method": spec.method,
                "targets": list(spec.targets),
            },
        )
        self._registry.upsert_factor_dataset(rec)
        man = FactorDatasetManifest(
            factor_code=code,
            factor_version=version,
            factor_hash=nhash,
            dataset_hash=dataset_hash,
            snapshot_id=rec.snapshot_id,
            schema_version="factor_daily_long@1",
            min_date=start,
            max_date=end,
            universe=universe_code,
            row_count=total,
            checksum=fac_checksum,
            layout="long",
            engine="neutralization",
            engine_version=spec.neutralization_version,
            factor_dataset_id=fid,
            frequency="1d",
            storage_uri=rec.storage_uri,
            metadata=dict(rec.metadata or {}),
        )
        self._factor_arts.write_manifest(man, record=rec)
        return neut_ref, fid, rec

    def _write_dated(
        self,
        nhash: str,
        _label: str,
        rows: list[dict[str, Any]],
        version: str,
        writer_fn,
    ) -> list[str]:
        by_ym: dict[tuple[int, int], list] = defaultdict(list)
        for r in rows:
            day = str(r.get("trading_date") or r.get("evaluation_date"))[:10]
            by_ym[(int(day[:4]), int(day[5:7]))].append(r)
        checksums = []
        for (y, m), part in sorted(by_ym.items()):
            written = writer_fn(
                self._store,
                part,
                neutralization_hash=nhash,
                year=y,
                month=m,
                version=version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
        return checksums
