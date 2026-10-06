"""FactorCombinationService：多 FactorDataset → Composite Factor Dataset。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.canonical_repository import CanonicalRepository
from app.services.research_data.contracts import (
    FactorCombinationSummary,
    FactorDatasetRecord,
)
from app.services.research_data.registry import ResearchRegistry

from .align import CrossSectionAligner
from .artifact_store import CombinationArtifactStore
from .combiner import WeightedCombiner
from .correlation import CorrelationRedundancyCalculator
from .hash import compute_combination_hash
from .normalize import CSNormalizer
from .orthogonalize import GramSchmidtOrtho
from .protocol import CombinationFrames, CombinationSpec
from .weighting import WeightSolver, WeightSolverError
from .writers import CombinationDatasetWriter


class FactorCombinationError(RuntimeError):
    """因子组合失败。"""


@dataclass
class CombinationResult:
    """组合运行结果。"""

    combination_hash: str
    frames: CombinationFrames
    summary: FactorCombinationSummary
    composite_factor_dataset_id: str
    members: dict[str, FactorDatasetRecord | None] | None = None


class FactorCombinationService:
    """Factor Transformation；不复制 Evaluation；不覆盖成员 Dataset。"""

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        artifact_store: CombinationArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifact_store or CombinationArtifactStore()
        self._aligner = CrossSectionAligner()
        self._normalizer = CSNormalizer()
        self._corr = CorrelationRedundancyCalculator()
        self._weights = WeightSolver()
        self._combiner = WeightedCombiner()
        self._ortho = GramSchmidtOrtho()
        self._writer = CombinationDatasetWriter(
            store, registry, artifact_store=self._artifacts
        )

    def run(
        self,
        member_factor_dataset_ids: list[str] | None = None,
        spec: CombinationSpec | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> CombinationResult:
        """端到端：resolve → align → normalize → corr → weight/ortho → dual write。"""
        meta = dict(metadata or {})
        # 合并 IC：spec.member_ic 优先，其次 metadata
        if spec is None:
            ids = list(member_factor_dataset_ids or [])
            if len(ids) < 2:
                raise FactorCombinationError(
                    "member_factor_dataset_ids must have >= 2 ids"
                )
            ic = dict(meta.get("member_ic") or {})
            spec = CombinationSpec(
                member_factor_dataset_ids=ids,
                member_ic=ic,
                normalize=str(meta.get("normalize") or "RANK"),
                weight_method=str(meta.get("weight_method") or "EQUAL"),
                redundancy_corr_threshold=float(
                    meta.get("redundancy_corr_threshold") or 0.7
                ),
                min_cross_section_size=int(meta.get("min_cross_section_size") or 30),
                metadata=dict(meta.get("spec_metadata") or {}),
            )
        else:
            if member_factor_dataset_ids is not None:
                if list(member_factor_dataset_ids) != list(
                    spec.member_factor_dataset_ids
                ):
                    spec = spec.model_copy(
                        update={
                            "member_factor_dataset_ids": list(member_factor_dataset_ids)
                        }
                    )
            if meta.get("member_ic") and not spec.member_ic:
                spec = spec.model_copy(update={"member_ic": dict(meta["member_ic"])})

        members = self._resolve_members(spec, meta)
        member_hashes = {
            mid: (
                (rec.dataset_hash if rec else "")
                or (rec.factor_hash if rec else "")
                or str((meta.get("member_hashes") or {}).get(mid) or "injected")
            )
            for mid, rec in members.items()
        }
        chash = compute_combination_hash(spec, member_hashes=member_hashes)
        force = bool(meta.get("force_recompute"))

        injected = meta.get("member_records")
        if not force and injected is None:
            try:
                summary = self._registry.get_factor_combination(chash)
                return CombinationResult(
                    combination_hash=chash,
                    frames=CombinationFrames(
                        combination_hash=chash,
                        member_ids=list(spec.member_factor_dataset_ids),
                    ),
                    summary=summary,
                    composite_factor_dataset_id=summary.composite_factor_dataset_id,
                    members=members,
                )
            except KeyError:
                pass

        panels = self._load_panels(members, meta)
        aligned = self._aligner.align(panels, spec)
        if not aligned:
            raise FactorCombinationError(
                "align produced no rows "
                "(check DROP_ROW overlap / min_cross_section_size)"
            )
        normalized = self._normalizer.normalize(aligned, spec)
        if not normalized:
            raise FactorCombinationError("normalize produced no rows")

        corr_cells, red_pairs, corr_summary = self._corr.calculate(normalized, spec)

        try:
            weights = self._weights.solve(
                spec,
                corr_matrix=corr_summary.get("matrix"),
                member_ic=spec.member_ic,
            )
        except WeightSolverError as exc:
            raise FactorCombinationError(str(exc)) from exc

        if spec.weight_method == "ORTHOGONALIZE":
            composite_rows = self._ortho.combine(normalized, spec)
        else:
            composite_rows = self._combiner.combine(normalized, weights, spec)

        if not composite_rows:
            raise FactorCombinationError("composite produced no rows")

        frames = CombinationFrames(
            combination_hash=chash,
            member_ids=list(spec.member_factor_dataset_ids),
            composite_rows=composite_rows,
            corr_cells=corr_cells,
            redundancy_pairs=red_pairs,
            weights=weights,
            metadata={"corr_summary": corr_summary},
        )

        # 取首个成员的 snapshot/universe 作为 composite 元数据默认值
        first = next(
            (members[m] for m in spec.member_factor_dataset_ids if members.get(m)),
            None,
        )
        summary = self._writer.write(
            spec,
            frames,
            member_hashes=member_hashes,
            snapshot_id=(
                first.snapshot_id
                if first
                else str(meta.get("snapshot_id") or "")
            ),
            universe_code=(
                first.universe_code
                if first
                else str(meta.get("universe_code") or "")
            ),
            force=force,
            corr_summary=corr_summary,
        )
        return CombinationResult(
            combination_hash=chash,
            frames=frames,
            summary=summary,
            composite_factor_dataset_id=summary.composite_factor_dataset_id,
            members=members,
        )

    def _resolve_members(
        self, spec: CombinationSpec, meta: dict[str, Any]
    ) -> dict[str, FactorDatasetRecord | None]:
        out: dict[str, FactorDatasetRecord | None] = {}
        injected = meta.get("member_records") or {}
        for mid in spec.member_factor_dataset_ids:
            try:
                out[mid] = self._registry.get_factor_dataset(mid)
            except KeyError:
                if mid in injected or meta.get("member_hashes"):
                    out[mid] = None
                else:
                    raise FactorCombinationError(
                        f"factor_dataset not found: {mid}"
                    ) from None
        return out

    def _load_panels(
        self,
        members: dict[str, FactorDatasetRecord | None],
        meta: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        injected = meta.get("member_records")
        if injected is not None:
            return {mid: list(injected[mid]) for mid in members}

        from app.services.research_data import config as rd_config

        panels: dict[str, list[dict[str, Any]]] = {}
        for mid, rec in members.items():
            if rec is None:
                raise FactorCombinationError(f"no factor rows for {mid}")
            prefix = (
                f"{rd_config.canonical_prefix()}/factor/daily/factor_set={rec.factor_ref}"
            )
            try:
                df = CanonicalRepository(self._store).read_parquet_df(prefix=prefix)
            except Exception as exc:
                raise FactorCombinationError(
                    f"failed to load factor panel for {mid}"
                ) from exc
            if df is None or df.empty:
                raise FactorCombinationError(f"empty factor panel for {mid}")
            panels[mid] = df.to_dict(orient="records")
        return panels
