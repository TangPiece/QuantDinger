"""StrategyResearchService：Factor + 4I → 冻结 Strategy Contract。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.canonical_repository import CanonicalRepository
from app.services.research_data.contracts import (
    FactorDatasetRecord,
    FactorPortfolioSummary,
    StrategyResearchSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import StrategyArtifactStore
from .binder import PortfolioPositionBinder
from .hash import compute_strategy_hash
from .lookahead import LookAheadError, assert_no_lookahead
from .protocol import (
    HoldingRule,
    RebalanceRule,
    SignalDefinition,
    StrategyFrames,
    StrategySpec,
)
from .signal_builder import FactorSignalBuilder
from .writers import StrategyDatasetWriter


class StrategyResearchError(RuntimeError):
    """策略研究物化失败。"""


@dataclass
class StrategyResult:
    strategy_hash: str
    frames: StrategyFrames
    summary: StrategyResearchSummary
    factor: FactorDatasetRecord | None = None
    portfolio: FactorPortfolioSummary | None = None


class StrategyResearchService:
    """物化 Strategy Contract；不算收益、不撮合。"""

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        artifact_store: StrategyArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifact_store or StrategyArtifactStore()
        self._signals = FactorSignalBuilder()
        self._binder = PortfolioPositionBinder()
        self._writer = StrategyDatasetWriter(
            store, registry, artifact_store=self._artifacts
        )

    def materialize(
        self,
        strategy_code: str,
        spec: StrategySpec | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> StrategyResult:
        """resolve → validate → signals → lookahead → bind → write。"""
        meta = dict(metadata or {})
        if spec is None:
            phash = str(meta.get("portfolio_hash") or "")
            fid = str(meta.get("factor_dataset_id") or "")
            if not phash or not fid:
                raise StrategyResearchError(
                    "portfolio_hash and factor_dataset_id required"
                )
            freq = str(meta.get("rebalance_frequency") or "DAILY")
            day = "FRIDAY" if freq == "WEEKLY" else (
                "LAST_IN_PERIOD" if freq == "MONTHLY" else "FIRST_IN_PERIOD"
            )
            spec = StrategySpec(
                strategy_code=strategy_code,
                strategy_name=str(meta.get("strategy_name") or strategy_code),
                factor_dataset_id=fid,
                portfolio_hash=phash,
                signal_definition=SignalDefinition(factor_dataset_id=fid),
                rebalance_rule=RebalanceRule(
                    frequency=freq,  # type: ignore[arg-type]
                    rebalance_day=day,  # type: ignore[arg-type]
                ),
                holding_rule=HoldingRule(),
                universe_code=str(meta.get("universe_code") or ""),
                snapshot_id=str(meta.get("snapshot_id") or ""),
            )
        elif spec.strategy_code != strategy_code:
            spec = spec.model_copy(update={"strategy_code": strategy_code})

        factor = self._resolve_factor(spec.factor_dataset_id, meta)
        fhash = (
            (factor.dataset_hash if factor else "")
            or (factor.factor_hash if factor else "")
            or str(meta.get("factor_dataset_hash") or "injected")
        )
        if not spec.universe_code and factor is not None:
            spec = spec.model_copy(update={"universe_code": factor.universe_code or ""})
        if not spec.snapshot_id and factor is not None:
            spec = spec.model_copy(update={"snapshot_id": factor.snapshot_id or ""})

        portfolio = self._resolve_portfolio(spec.portfolio_hash, meta)
        self._validate_binding(spec, portfolio)

        shash = compute_strategy_hash(spec, factor_dataset_hash=fhash)
        force = bool(meta.get("force_recompute"))
        if (
            not force
            and meta.get("factor_records") is None
            and meta.get("portfolio_positions") is None
            and factor is not None
            and portfolio is not None
        ):
            try:
                summary = self._registry.get_strategy_research(shash)
                return StrategyResult(
                    strategy_hash=shash,
                    frames=StrategyFrames(
                        strategy_hash=shash, strategy_code=strategy_code
                    ),
                    summary=summary,
                    factor=factor,
                    portfolio=portfolio,
                )
            except KeyError:
                pass

        factor_rows = self._load_factor_rows(factor, meta)
        signals = self._signals.build(
            factor_rows,
            spec,
            strategy_hash=shash,
            factor_dataset_hash=fhash,
        )
        if not signals:
            raise StrategyResearchError("no signals produced from factor panel")
        try:
            assert_no_lookahead(signals)
        except LookAheadError as exc:
            raise StrategyResearchError(str(exc)) from exc

        port_rows = self._load_portfolio_positions(spec.portfolio_hash, meta)
        if not port_rows:
            raise StrategyResearchError(
                f"no portfolio positions for {spec.portfolio_hash}"
            )
        positions = self._binder.bind(
            port_rows,
            spec,
            strategy_hash=shash,
            factor_dataset_hash=fhash,
            signals=signals,
        )
        legs = {
            (
                str(r.get("trading_date"))[:10],
                str(r["instrument_key"]),
            ): str(r.get("leg") or "")
            for r in port_rows
        }
        frames = StrategyFrames(
            strategy_hash=shash,
            strategy_code=strategy_code,
            signals=signals,
            positions=positions,
        )
        summary = self._writer.write(
            spec,
            frames,
            portfolio_summary_meta={
                "evaluation_hash": (
                    portfolio.evaluation_hash if portfolio else ""
                ),
            },
            position_legs=legs,
            force=force,
        )
        return StrategyResult(
            strategy_hash=shash,
            frames=frames,
            summary=summary,
            factor=factor,
            portfolio=portfolio,
        )

    def _validate_binding(
        self,
        spec: StrategySpec,
        portfolio: FactorPortfolioSummary | None,
    ) -> None:
        if portfolio is None:
            return
        if portfolio.factor_dataset_id != spec.factor_dataset_id:
            raise StrategyResearchError(
                f"portfolio.factor_dataset_id={portfolio.factor_dataset_id!r} "
                f"!= strategy.factor_dataset_id={spec.factor_dataset_id!r}"
            )
        if portfolio.rebalance_frequency != spec.rebalance_rule.frequency:
            raise StrategyResearchError(
                f"rebalance frequency mismatch: strategy="
                f"{spec.rebalance_rule.frequency!r} portfolio="
                f"{portfolio.rebalance_frequency!r}"
            )

    def _resolve_factor(
        self, factor_dataset_id: str, meta: dict[str, Any]
    ) -> FactorDatasetRecord | None:
        try:
            return self._registry.get_factor_dataset(factor_dataset_id)
        except KeyError:
            if meta.get("factor_records") is not None:
                return None
            raise StrategyResearchError(
                f"factor_dataset not found: {factor_dataset_id}"
            ) from None

    def _resolve_portfolio(
        self, portfolio_hash: str, meta: dict[str, Any]
    ) -> FactorPortfolioSummary | None:
        try:
            return self._registry.get_factor_portfolio(portfolio_hash)
        except KeyError:
            if meta.get("portfolio_positions") is not None:
                # 测试注入：用 meta 拼最小 Summary 供校验
                injected = meta.get("portfolio_summary")
                if isinstance(injected, FactorPortfolioSummary):
                    return injected
                if isinstance(injected, dict):
                    return FactorPortfolioSummary.model_validate(injected)
                return FactorPortfolioSummary(
                    portfolio_hash=portfolio_hash,
                    factor_dataset_id=str(
                        meta.get("factor_dataset_id")
                        or meta.get("injected_factor_dataset_id")
                        or ""
                    ),
                    rebalance_frequency=str(
                        meta.get("rebalance_frequency") or "DAILY"
                    ),
                    evaluation_hash=str(meta.get("evaluation_hash") or ""),
                )
            raise StrategyResearchError(
                f"factor_portfolio not found: {portfolio_hash}"
            ) from None

    def _load_factor_rows(
        self,
        factor: FactorDatasetRecord | None,
        meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if meta.get("factor_records") is not None:
            return list(meta["factor_records"])
        if factor is None:
            raise StrategyResearchError("no factor rows")
        from app.services.research_data import config as rd_config

        prefix = (
            f"{rd_config.canonical_prefix()}/factor/daily/factor_set={factor.factor_ref}"
        )
        try:
            df = CanonicalRepository(self._store).read_parquet_df(prefix=prefix)
        except Exception as exc:
            raise StrategyResearchError(
                f"failed to load factor panel for {factor.factor_dataset_id}"
            ) from exc
        if df is None or df.empty:
            raise StrategyResearchError("empty factor panel")
        return df.to_dict(orient="records")

    def _load_portfolio_positions(
        self, portfolio_hash: str, meta: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if meta.get("portfolio_positions") is not None:
            return list(meta["portfolio_positions"])
        from app.services.research_data import config as rd_config

        prefix = (
            f"{rd_config.canonical_prefix()}/portfolio/{portfolio_hash}/positions"
        )
        try:
            df = CanonicalRepository(self._store).read_parquet_df(prefix=prefix)
        except Exception as exc:
            raise StrategyResearchError(
                f"failed to load portfolio positions {portfolio_hash}"
            ) from exc
        if df is None or df.empty:
            return []
        return df.to_dict(orient="records")
