"""FactorPortfolioService：FactorDataset → Target Portfolio + 理论绩效。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.canonical_repository import CanonicalRepository
from app.services.research_data.contracts import (
    EvaluationDatasetRecord,
    FactorDatasetRecord,
    FactorPortfolioSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import PortfolioArtifactStore
from .hash import compute_portfolio_hash
from .metrics import PortfolioMetricsCalculator
from .protocol import PortfolioFrames, PortfolioSpec
from .rebalance import RebalanceEngine
from .returns import PortfolioReturnCalculator
from .selector import PortfolioSelector
from .writers import PortfolioDatasetWriter


class FactorPortfolioError(RuntimeError):
    """因子组合构建失败。"""


@dataclass
class PortfolioResult:
    """组合运行结果。"""

    portfolio_hash: str
    frames: PortfolioFrames
    summary: FactorPortfolioSummary
    factor: FactorDatasetRecord | None = None
    evaluation: EvaluationDatasetRecord | None = None


class FactorPortfolioService:
    """Factor → TargetPosition 轨迹；非 Production Backtest。"""

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        artifact_store: PortfolioArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifact_store or PortfolioArtifactStore()
        self._selector = PortfolioSelector()
        self._rebalance = RebalanceEngine()
        self._returns = PortfolioReturnCalculator()
        self._metrics = PortfolioMetricsCalculator()
        self._writer = PortfolioDatasetWriter(
            store, registry, artifact_store=self._artifacts
        )

    def run(
        self,
        factor_dataset_id: str,
        spec: PortfolioSpec | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> PortfolioResult:
        """端到端：load → select → rebalance → returns → metrics → write。"""
        meta = dict(metadata or {})
        if spec is None:
            ehash = str(meta.get("evaluation_hash") or "")
            if not ehash:
                raise FactorPortfolioError("evaluation_hash required")
            spec = PortfolioSpec(
                factor_dataset_id=factor_dataset_id,
                evaluation_hash=ehash,
                construction_method=str(
                    meta.get("construction_method") or "LONG_ONLY"
                ),
                weight_method=str(meta.get("weight_method") or "EQUAL_WEIGHT"),
                selection_mode=str(meta.get("selection_mode") or "TOP_PCT"),
                top_n=meta.get("top_n"),
                top_pct=meta.get("top_pct", 0.1),
                group_count=int(meta.get("group_count") or 5),
                rebalance_frequency=str(
                    meta.get("rebalance_frequency") or "DAILY"
                ),
                horizon=int(meta.get("horizon") or 1),
                min_turnover=float(meta.get("min_turnover") or 0.005),
                min_cross_section_size=int(
                    meta.get("min_cross_section_size") or 30
                ),
                direction=str(meta.get("direction") or "POSITIVE"),
            )
        elif spec.factor_dataset_id != factor_dataset_id:
            spec = spec.model_copy(
                update={"factor_dataset_id": factor_dataset_id}
            )

        factor = self._resolve_factor(factor_dataset_id, meta)
        fhash = (
            (factor.dataset_hash if factor else "")
            or (factor.factor_hash if factor else "")
            or str(meta.get("factor_dataset_hash") or "injected")
        )
        phash = compute_portfolio_hash(spec, factor_dataset_hash=fhash)
        force = bool(meta.get("force_recompute"))

        if (
            not force
            and meta.get("factor_records") is None
            and meta.get("evaluation_records") is None
            and factor is not None
        ):
            try:
                summary = self._registry.get_factor_portfolio(phash)
                return PortfolioResult(
                    portfolio_hash=phash,
                    frames=PortfolioFrames(
                        portfolio_hash=phash,
                        factor_dataset_id=factor_dataset_id,
                        evaluation_hash=spec.evaluation_hash,
                    ),
                    summary=summary,
                    factor=factor,
                )
            except KeyError:
                pass

        factor_rows = self._load_factor_rows(factor, meta)
        eval_rows = self._load_eval_rows(spec, meta)
        if not eval_rows:
            raise FactorPortfolioError(
                "evaluation forward returns required "
                f"(forward_return_{spec.horizon}d)"
            )

        candidates = self._selector.select_all(factor_rows, spec)
        if not candidates:
            raise FactorPortfolioError(
                "selector produced no positions "
                "(check min_cross_section_size / factor panel)"
            )
        positions, turnover = self._rebalance.apply(candidates, spec)
        returns = self._returns.calculate(positions, eval_rows, spec)
        metrics = self._metrics.calculate(
            returns,
            turnover,
            construction_method=spec.construction_method,
        )
        frames = PortfolioFrames(
            portfolio_hash=phash,
            factor_dataset_id=factor_dataset_id,
            evaluation_hash=spec.evaluation_hash,
            positions=positions,
            returns=returns,
            turnover=turnover,
            metrics=metrics,
        )
        summary = self._writer.write(
            spec, frames, factor_dataset_hash=fhash, force=force
        )
        eval_rec = None
        try:
            eval_rec = self._registry.get_evaluation_dataset(spec.evaluation_hash)
        except Exception:
            pass
        return PortfolioResult(
            portfolio_hash=phash,
            frames=frames,
            summary=summary,
            factor=factor,
            evaluation=eval_rec,
        )

    def _resolve_factor(
        self, factor_dataset_id: str, meta: dict[str, Any]
    ) -> FactorDatasetRecord | None:
        try:
            return self._registry.get_factor_dataset(factor_dataset_id)
        except KeyError:
            if meta.get("factor_records") is not None:
                return None
            raise FactorPortfolioError(
                f"factor_dataset not found: {factor_dataset_id}"
            ) from None

    def _load_factor_rows(
        self,
        factor: FactorDatasetRecord | None,
        meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if meta.get("factor_records") is not None:
            return list(meta["factor_records"])
        if factor is None:
            raise FactorPortfolioError("no factor rows")
        from app.services.research_data import config as rd_config

        prefix = (
            f"{rd_config.canonical_prefix()}/factor/daily/factor_set={factor.factor_ref}"
        )
        try:
            df = CanonicalRepository(self._store).read_parquet_df(prefix=prefix)
        except Exception as exc:
            raise FactorPortfolioError(
                f"failed to load factor panel for {factor.factor_dataset_id}"
            ) from exc
        if df is None or df.empty:
            raise FactorPortfolioError("empty factor panel")
        return df.to_dict(orient="records")

    def _load_eval_rows(
        self, spec: PortfolioSpec, meta: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if meta.get("evaluation_records") is not None:
            return list(meta["evaluation_records"])
        from app.services.research_data import config as rd_config

        prefix = (
            f"{rd_config.canonical_prefix()}/evaluation/factor/{spec.evaluation_hash}"
        )
        try:
            df = CanonicalRepository(self._store).read_parquet_df(prefix=prefix)
        except Exception as exc:
            raise FactorPortfolioError(
                f"failed to load evaluation panel {spec.evaluation_hash}"
            ) from exc
        if df is None or df.empty:
            raise FactorPortfolioError("empty evaluation panel")
        return df.to_dict(orient="records")
