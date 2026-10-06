"""GroupFrames → Parquet + Manifest + Registry。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import GroupEvaluationSummary
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data import writer as rd_writer

from .artifact_store import GroupArtifactStore
from .protocol import GroupFrames, GroupManifest, GroupSpec


class GroupDatasetWriter:
    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        artifact_store: GroupArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifact_store or GroupArtifactStore()

    def write(
        self,
        spec: GroupSpec,
        frames: GroupFrames,
        summaries: list[GroupEvaluationSummary],
        *,
        factor_dataset_id: str = "",
        force: bool = False,
    ) -> list[GroupEvaluationSummary]:
        ghash = frames.group_evaluation_hash
        if not force and summaries:
            try:
                existing = self._registry.get_factor_group_evaluation(
                    ghash, summaries[0].horizon
                )
                if existing.group_evaluation_hash == ghash:
                    out = []
                    for s in summaries:
                        try:
                            out.append(
                                self._registry.get_factor_group_evaluation(
                                    ghash, s.horizon
                                )
                            )
                        except KeyError:
                            out.append(s)
                    return out
            except (KeyError, AttributeError):
                pass

        checksums: list[str] = []
        checksums += self._write_kind(
            ghash,
            "membership",
            [m.model_dump(mode="json") for m in frames.membership],
            spec.group_version,
            rd_writer.write_group_membership_panel,
        )
        checksums += self._write_kind(
            ghash,
            "returns",
            [r.model_dump(mode="json") for r in frames.returns],
            spec.group_version,
            rd_writer.write_group_return_panel,
        )
        checksums += self._write_kind(
            ghash,
            "turnover",
            [t.model_dump(mode="json") for t in frames.turnover],
            spec.group_version,
            rd_writer.write_group_turnover_panel,
        )
        checksum = hashlib.sha256("".join(checksums or ["empty"]).encode()).hexdigest()
        man = GroupManifest(
            group_evaluation_hash=ghash,
            evaluation_hash=frames.evaluation_hash,
            factor_dataset_id=factor_dataset_id,
            group_spec=spec.model_dump(mode="json"),
            horizons=list(frames.horizons),
            membership_rows=len(frames.membership),
            return_rows=len(frames.returns),
            turnover_rows=len(frames.turnover),
            checksum=checksum,
            group_version=spec.group_version,
            metadata={"direction": frames.direction},
        )
        art = self._artifacts.write_manifest(man, summaries=summaries)
        out: list[GroupEvaluationSummary] = []
        for s in summaries:
            rec = s.model_copy(
                update={
                    "storage_uri": art.storage_uri,
                    "checksum": art.checksum,
                    "factor_dataset_id": factor_dataset_id or s.factor_dataset_id,
                }
            )
            self._registry.upsert_factor_group_evaluation(rec)
            out.append(rec)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return out

    def _write_kind(
        self,
        ghash: str,
        _label: str,
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
                group_evaluation_hash=ghash,
                year=y,
                month=m,
                version=version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
        return checksums
