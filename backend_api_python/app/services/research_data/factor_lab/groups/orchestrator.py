"""FactorGroupEvaluationService：Evaluation Dataset → Group Evaluation。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.canonical_repository import CanonicalRepository
from app.services.research_data.contracts import (
    EvaluationDatasetRecord,
    GroupEvaluationSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .aggregator import GroupEvaluationAggregator
from .artifact_store import GroupArtifactStore
from .assigner import GroupAssigner, infer_horizons
from .cost import CostCalculator
from .hash import compute_group_evaluation_hash
from .protocol import GroupFrames, GroupSpec
from .returns import GroupReturnCalculator
from .turnover import TurnoverCalculator
from .writers import GroupDatasetWriter


class FactorGroupEvaluationError(RuntimeError):
    """分组评价失败。"""


@dataclass
class GroupEvaluationResult:
    group_evaluation_hash: str
    frames: GroupFrames
    summaries: list[GroupEvaluationSummary]
    evaluation: EvaluationDatasetRecord | None = None
    direction: Literal["POSITIVE", "NEGATIVE"] = "POSITIVE"


class FactorGroupEvaluationService:
    """只消费 4C Evaluation Dataset；非 Production Backtest。"""

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
        self._assigner = GroupAssigner()
        self._returns = GroupReturnCalculator()
        self._turnover = TurnoverCalculator()
        self._cost = CostCalculator()
        self._agg = GroupEvaluationAggregator()
        self._writer = GroupDatasetWriter(
            store, registry, artifact_store=self._artifacts
        )

    def run(
        self,
        evaluation_hash: str,
        spec: GroupSpec | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> GroupEvaluationResult:
        meta = dict(metadata or {})
        try:
            eval_rec = self._registry.get_evaluation_dataset(evaluation_hash)
        except KeyError as exc:
            if meta.get("evaluation_records") is None:
                raise FactorGroupEvaluationError(
                    f"evaluation_dataset not found: {evaluation_hash}"
                ) from exc
            eval_rec = None

        gspec = spec or GroupSpec(evaluation_hash=evaluation_hash)
        if gspec.evaluation_hash != evaluation_hash:
            gspec = gspec.model_copy(update={"evaluation_hash": evaluation_hash})

        direction = self._resolve_direction(gspec, eval_rec, meta)
        ghash = compute_group_evaluation_hash(gspec, resolved_direction=direction)
        force = bool(meta.get("force_recompute"))

        if not force and meta.get("evaluation_records") is None and eval_rec is not None:
            try:
                horizons = gspec.horizons or [1]
                summaries = [
                    self._registry.get_factor_group_evaluation(ghash, h)
                    for h in horizons
                ]
                return GroupEvaluationResult(
                    group_evaluation_hash=ghash,
                    frames=GroupFrames(
                        group_evaluation_hash=ghash,
                        evaluation_hash=evaluation_hash,
                        horizons=list(horizons),
                        direction=direction,
                    ),
                    summaries=summaries,
                    evaluation=eval_rec,
                    direction=direction,
                )
            except KeyError:
                pass

        records = self._load_records(evaluation_hash, meta)
        horizons = list(gspec.horizons) if gspec.horizons else infer_horizons(records)
        membership = self._assigner.assign(records, gspec)
        rets = self._returns.calculate(
            membership, records, gspec, direction=direction
        )
        turns = self._turnover.calculate(membership, gspec, direction=direction)
        rets = self._cost.apply(rets, turns, gspec.cost_model)
        frames = GroupFrames(
            group_evaluation_hash=ghash,
            evaluation_hash=evaluation_hash,
            horizons=horizons,
            membership=membership,
            returns=rets,
            turnover=turns,
            direction=direction,
        )
        factor_ds_id = (
            (eval_rec.factor_dataset_id if eval_rec else "")
            or str(meta.get("factor_dataset_id") or "")
        )
        summaries = self._agg.aggregate(
            frames, gspec, direction=direction, factor_dataset_id=factor_ds_id
        )
        written = self._writer.write(
            gspec,
            frames,
            summaries,
            factor_dataset_id=factor_ds_id,
            force=force,
        )
        return GroupEvaluationResult(
            group_evaluation_hash=ghash,
            frames=frames,
            summaries=written,
            evaluation=eval_rec,
            direction=direction,
        )

    def _resolve_direction(
        self,
        spec: GroupSpec,
        eval_rec: EvaluationDatasetRecord | None,
        meta: dict[str, Any],
    ) -> Literal["POSITIVE", "NEGATIVE"]:
        if spec.direction in ("POSITIVE", "NEGATIVE"):
            return spec.direction  # type: ignore[return-value]
        # AUTO：从 metadata / evaluation metadata 继承，禁止猜测
        cand = meta.get("resolved_direction") or meta.get("direction")
        if not cand and isinstance(spec.metadata, dict):
            cand = spec.metadata.get("direction")
        if not cand and eval_rec is not None:
            cand = (eval_rec.metadata or {}).get("direction")
        if cand in ("POSITIVE", "NEGATIVE"):
            return cand
        raise FactorGroupEvaluationError(
            "direction=AUTO could not be resolved; "
            "set GroupSpec.direction to POSITIVE/NEGATIVE or pass "
            "metadata['resolved_direction']"
        )

    def _load_records(
        self, evaluation_hash: str, meta: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if meta.get("evaluation_records") is not None:
            return list(meta["evaluation_records"])
        from app.services.research_data import config as rd_config

        prefix = (
            f"{rd_config.canonical_prefix()}/evaluation/factor/{evaluation_hash}"
        )
        try:
            df = CanonicalRepository(self._store).read_parquet_df(prefix=prefix)
        except Exception as exc:
            raise FactorGroupEvaluationError(
                f"failed to load evaluation panel for {evaluation_hash}"
            ) from exc
        if df is None or df.empty:
            raise FactorGroupEvaluationError(
                f"empty evaluation panel: {evaluation_hash}"
            )
        return df.to_dict(orient="records")
