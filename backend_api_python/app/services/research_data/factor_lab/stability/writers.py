"""StabilityFrames → Parquet + Manifest + Registry。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import FactorStabilitySummary
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data import writer as rd_writer

from .artifact_store import StabilityArtifactStore
from .protocol import StabilityFrames, StabilityManifest, StabilitySpec


class StabilityDatasetWriter:
    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        artifact_store: StabilityArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifact_store or StabilityArtifactStore()

    def write(
        self,
        spec: StabilitySpec,
        frames: StabilityFrames,
        summaries: list[FactorStabilitySummary],
        *,
        factor_dataset_id: str = "",
        force: bool = False,
    ) -> list[FactorStabilitySummary]:
        shash = frames.stability_hash
        if not force and summaries:
            try:
                existing = self._registry.get_factor_stability_evaluation(
                    shash, summaries[0].horizon
                )
                if existing.stability_hash == shash:
                    out = []
                    for s in summaries:
                        try:
                            out.append(
                                self._registry.get_factor_stability_evaluation(
                                    shash, s.horizon
                                )
                            )
                        except KeyError:
                            out.append(s)
                    return out
            except (KeyError, AttributeError):
                pass

        checksums: list[str] = []
        checksums += self._write_dated(
            shash,
            [r.model_dump(mode="json") for r in frames.rolling_ic],
            spec.stability_version,
            rd_writer.write_rolling_ic_panel,
        )
        if frames.decay:
            written = rd_writer.write_decay_curve_panel(
                self._store,
                [d.model_dump(mode="json") for d in frames.decay],
                stability_hash=shash,
                version=spec.stability_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
        checksums += self._write_dated(
            shash,
            [g.model_dump(mode="json") for g in frames.group_stability],
            spec.stability_version,
            rd_writer.write_group_stability_panel,
        )
        if frames.regime:
            written = rd_writer.write_regime_metrics_panel(
                self._store,
                [r.model_dump(mode="json") for r in frames.regime],
                stability_hash=shash,
                version=spec.stability_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])

        checksum = hashlib.sha256("".join(checksums or ["empty"]).encode()).hexdigest()
        man = StabilityManifest(
            stability_hash=shash,
            evaluation_hash=frames.evaluation_hash,
            factor_dataset_id=factor_dataset_id,
            stability_spec=spec.model_dump(mode="json"),
            horizons=list(frames.horizons),
            rolling_rows=len(frames.rolling_ic),
            decay_rows=len(frames.decay),
            group_stability_rows=len(frames.group_stability),
            regime_rows=len(frames.regime),
            checksum=checksum,
            stability_version=spec.stability_version,
            metadata={"direction": frames.direction},
        )
        art = self._artifacts.write_manifest(man, summaries=summaries)
        out: list[FactorStabilitySummary] = []
        for s in summaries:
            rec = s.model_copy(
                update={
                    "storage_uri": art.storage_uri,
                    "checksum": art.checksum,
                    "factor_dataset_id": factor_dataset_id or s.factor_dataset_id,
                }
            )
            self._registry.upsert_factor_stability_evaluation(rec)
            out.append(rec)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return out

    def _write_dated(
        self,
        shash: str,
        rows: list[dict[str, Any]],
        version: str,
        writer_fn,
    ) -> list[str]:
        by_ym: dict[tuple[int, int], list] = defaultdict(list)
        for r in rows:
            day = str(r["evaluation_date"])[:10]
            by_ym[(int(day[:4]), int(day[5:7]))].append(r)
        checksums = []
        for (y, m), part in sorted(by_ym.items()):
            written = writer_fn(
                self._store,
                part,
                stability_hash=shash,
                year=y,
                month=m,
                version=version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
        return checksums
