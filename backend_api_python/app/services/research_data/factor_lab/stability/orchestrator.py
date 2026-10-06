"""FactorStabilityService：Evaluation Dataset → Stability / Decay。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.canonical_repository import CanonicalRepository
from app.services.research_data.contracts import (
    EvaluationDatasetRecord,
    FactorStabilitySummary,
)
from app.services.research_data.factor_lab.groups.assigner import (
    GroupAssigner,
    infer_horizons as infer_group_horizons,
)
from app.services.research_data.factor_lab.groups.cost import CostCalculator
from app.services.research_data.factor_lab.groups.protocol import GroupFrames, GroupSpec
from app.services.research_data.factor_lab.groups.returns import GroupReturnCalculator
from app.services.research_data.factor_lab.groups.turnover import TurnoverCalculator
from app.services.research_data.factor_lab.metrics.calculators import (
    CrossSectionalICEngine,
    infer_horizons as infer_metric_horizons,
)
from app.services.research_data.factor_lab.metrics.protocol import MetricPoint, MetricSpec
from app.services.research_data.registry import ResearchRegistry

from .aggregator import StabilityAggregator
from .artifact_store import StabilityArtifactStore
from .decay import DecayCalculator
from .distribution import ICDistributionCalculator
from .group_stability import GroupStabilityCalculator
from .hash import compute_stability_hash
from .protocol import (
    DEFAULT_DECAY_HORIZONS,
    StabilityFrames,
    StabilitySpec,
)
from .regime import RegimeStabilityCalculator
from .rolling import RollingICCalculator
from .writers import StabilityDatasetWriter


class FactorStabilityError(RuntimeError):
    """稳定性评价失败。"""


@dataclass
class StabilityResult:
    """稳定性运行结果。"""

    stability_hash: str
    frames: StabilityFrames
    summaries: list[FactorStabilitySummary]
    evaluation: EvaluationDatasetRecord | None = None
    direction: Literal["POSITIVE", "NEGATIVE"] = "POSITIVE"


class FactorStabilityService:
    """只消费 4C；复用 4D IC 引擎与 4E Assigner/Returns，不短路空 frames。"""

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
        self._ic_engine = CrossSectionalICEngine()
        self._assigner = GroupAssigner()
        self._returns = GroupReturnCalculator()
        self._turnover = TurnoverCalculator()
        self._cost = CostCalculator()
        self._rolling = RollingICCalculator()
        self._dist = ICDistributionCalculator()
        self._decay = DecayCalculator()
        self._gstab = GroupStabilityCalculator()
        self._regime = RegimeStabilityCalculator()
        self._agg = StabilityAggregator()
        self._writer = StabilityDatasetWriter(
            store, registry, artifact_store=self._artifacts
        )

    def run(
        self,
        evaluation_hash: str,
        spec: StabilitySpec | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> StabilityResult:
        """端到端：IC → Group → Rolling/Decay/Regime → persist。"""
        meta = dict(metadata or {})
        try:
            eval_rec = self._registry.get_evaluation_dataset(evaluation_hash)
        except KeyError as exc:
            if meta.get("evaluation_records") is None:
                raise FactorStabilityError(
                    f"evaluation_dataset not found: {evaluation_hash}"
                ) from exc
            eval_rec = None

        sspec = spec or StabilitySpec(evaluation_hash=evaluation_hash)
        if sspec.evaluation_hash != evaluation_hash:
            sspec = sspec.model_copy(update={"evaluation_hash": evaluation_hash})

        direction = self._resolve_direction(sspec, eval_rec, meta)
        shash = compute_stability_hash(sspec, resolved_direction=direction)
        force = bool(meta.get("force_recompute"))

        if not force and meta.get("evaluation_records") is None and eval_rec is not None:
            try:
                horizons = sspec.decay_horizons or [1]
                summaries = [
                    self._registry.get_factor_stability_evaluation(shash, h)
                    for h in horizons
                ]
                return StabilityResult(
                    stability_hash=shash,
                    frames=StabilityFrames(
                        stability_hash=shash,
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
        panel_horizons = infer_metric_horizons(records) or [1]
        decay_horizons = (
            list(sspec.decay_horizons)
            if sspec.decay_horizons is not None
            else (
                [h for h in DEFAULT_DECAY_HORIZONS if h in set(panel_horizons)]
                or list(panel_horizons)
            )
        )

        # Daily IC：注入或同次计算（与 4D 同引擎）
        if meta.get("metric_points") is not None:
            metric_points = [
                p if isinstance(p, MetricPoint) else MetricPoint.model_validate(p)
                for p in meta["metric_points"]
            ]
        else:
            mspec = MetricSpec(
                evaluation_hash=evaluation_hash,
                horizons=decay_horizons,
                min_cross_section_size=sspec.min_cross_section_size,
                allowed_sample_status=list(sspec.allowed_sample_status),
                direction=direction,
            )
            series = self._ic_engine.calculate(
                records, mspec, metric_hash=f"stability:{shash}"
            )
            metric_points = list(series.points)

        # Group frames：注入或同次 Assigner+Returns（禁止依赖 4E cache 空 frames）
        if meta.get("group_frames") is not None:
            gframes = meta["group_frames"]
            if isinstance(gframes, dict):
                gframes = GroupFrames.model_validate(gframes)
            long_g = 1 if direction == "POSITIVE" else int(sspec.group_count)
            short_g = int(sspec.group_count) if direction == "POSITIVE" else 1
        else:
            gspec = GroupSpec(
                evaluation_hash=evaluation_hash,
                group_count=sspec.group_count,
                direction=direction,
                portfolio_mode=sspec.portfolio_mode,
                horizons=decay_horizons,
                min_cross_section_size=sspec.min_cross_section_size,
                allowed_sample_status=list(sspec.allowed_sample_status),
                cost_model=sspec.cost_model,
            )
            membership = self._assigner.assign(records, gspec)
            rets = self._returns.calculate(
                membership, records, gspec, direction=direction
            )
            turns = self._turnover.calculate(
                membership, gspec, direction=direction
            )
            rets = self._cost.apply(rets, turns, gspec.cost_model)
            long_g = 1 if direction == "POSITIVE" else int(sspec.group_count)
            short_g = int(sspec.group_count) if direction == "POSITIVE" else 1
            gframes = GroupFrames(
                group_evaluation_hash=f"stability:{shash}",
                evaluation_hash=evaluation_hash,
                horizons=decay_horizons or infer_group_horizons(records),
                membership=membership,
                returns=rets,
                turnover=turns,
                direction=direction,
            )

        rolling_rows = self._rolling.calculate(metric_points, sspec)
        distributions = self._dist.calculate(metric_points)
        decay_rows = self._decay.calculate(
            metric_points, list(gframes.returns), decay_horizons
        )
        gst_rows = self._gstab.calculate(
            list(gframes.returns),
            sspec,
            direction=direction,
            long_group=long_g,
            short_group=short_g,
        )
        regime_rows = self._regime.calculate(
            metric_points,
            list(gframes.returns),
            list(gframes.turnover),
            sspec,
        )

        frames = StabilityFrames(
            stability_hash=shash,
            evaluation_hash=evaluation_hash,
            horizons=decay_horizons,
            rolling_ic=rolling_rows,
            distributions=distributions,
            decay=decay_rows,
            group_stability=gst_rows,
            regime=regime_rows,
            metric_points=metric_points,
            direction=direction,
            metadata={"long_group": long_g, "short_group": short_g},
        )
        factor_ds_id = (
            (eval_rec.factor_dataset_id if eval_rec else "")
            or str(meta.get("factor_dataset_id") or "")
        )
        summaries = self._agg.aggregate(
            frames, sspec, factor_dataset_id=factor_ds_id, direction=direction
        )
        written = self._writer.write(
            sspec,
            frames,
            summaries,
            factor_dataset_id=factor_ds_id,
            force=force,
        )
        return StabilityResult(
            stability_hash=shash,
            frames=frames,
            summaries=written,
            evaluation=eval_rec,
            direction=direction,
        )

    def _resolve_direction(
        self,
        spec: StabilitySpec,
        eval_rec: EvaluationDatasetRecord | None,
        meta: dict[str, Any],
    ) -> Literal["POSITIVE", "NEGATIVE"]:
        if spec.direction in ("POSITIVE", "NEGATIVE"):
            return spec.direction  # type: ignore[return-value]
        cand = meta.get("resolved_direction") or meta.get("direction")
        if not cand and isinstance(spec.metadata, dict):
            cand = spec.metadata.get("direction")
        if not cand and eval_rec is not None:
            cand = (eval_rec.metadata or {}).get("direction")
        if cand in ("POSITIVE", "NEGATIVE"):
            return cand
        raise FactorStabilityError(
            "direction=AUTO could not be resolved; "
            "set StabilitySpec.direction or metadata['resolved_direction']"
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
            raise FactorStabilityError(
                f"failed to load evaluation panel for {evaluation_hash}"
            ) from exc
        if df is None or df.empty:
            raise FactorStabilityError(
                f"empty evaluation panel: {evaluation_hash}"
            )
        return df.to_dict(orient="records")
