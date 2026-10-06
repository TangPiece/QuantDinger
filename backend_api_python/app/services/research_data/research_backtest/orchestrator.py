"""ResearchBacktestService：5A Strategy → 研究回测 → R2/D1。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import (
    ResearchBacktestSummary,
    StrategyResearchSummary,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import BacktestArtifactStore
from .engine import ResearchBacktestEngine
from .hash import compute_backtest_hash
from .loader import load_price_bars, load_targets_by_date
from .protocol import (
    BacktestFrames,
    BacktestSpec,
    ResearchExecutionPolicy,
)
from .writers import BacktestDatasetWriter


class ResearchBacktestError(RuntimeError):
    """研究回测失败。"""


@dataclass
class BacktestResult:
    backtest_hash: str
    frames: BacktestFrames
    summary: ResearchBacktestSummary
    strategy: StrategyResearchSummary | None = None


class ResearchBacktestService:
    """消费 5A TargetPosition，产出研究 NAV/绩效；不撮合、无复杂成本。"""

    def __init__(
        self,
        store: CanonicalStore,
        registry: ResearchRegistry,
        *,
        artifact_store: BacktestArtifactStore | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifact_store or BacktestArtifactStore()
        self._engine = ResearchBacktestEngine()
        self._writer = BacktestDatasetWriter(
            store, registry, artifact_store=self._artifacts
        )

    def run(
        self,
        strategy_hash: str,
        spec: BacktestSpec | None = None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> BacktestResult:
        """resolve strategy → load targets/prices → simulate → write → register。"""
        meta = dict(metadata or {})
        strategy = self._resolve_strategy(strategy_hash, meta)
        if spec is None:
            start = _parse_date(meta.get("start_date"))
            end = _parse_date(meta.get("end_date"))
            if start is None or end is None:
                raise ResearchBacktestError(
                    "start_date and end_date required when spec is None"
                )
            mode = str(meta.get("execution_policy") or "NEXT_OPEN")
            spec = BacktestSpec(
                strategy_hash=strategy_hash,
                start_date=start,
                end_date=end,
                execution_policy=ResearchExecutionPolicy(mode=mode),  # type: ignore[arg-type]
                benchmark_mode=str(meta.get("benchmark_mode") or "NONE"),  # type: ignore[arg-type]
                benchmark_instrument_key=str(
                    meta.get("benchmark_instrument_key") or ""
                ),
                initial_nav=float(meta.get("initial_nav") or 1.0),
                exchange=str(meta.get("exchange") or "CN"),
                realism=str(meta.get("realism") or "GROSS"),  # type: ignore[arg-type]
                market_rule=str(meta.get("market_rule") or "CN_A"),  # type: ignore[arg-type]
                metadata={
                    k: meta[k]
                    for k in (
                        "cost_policy_override",
                        "trading_rule_override",
                    )
                    if k in meta
                },
            )
        elif spec.strategy_hash != strategy_hash:
            spec = spec.model_copy(update={"strategy_hash": strategy_hash})

        # 将费率/规则覆盖并入 Spec.metadata（进 hash）
        merge_keys = ("cost_policy_override", "trading_rule_override")
        if any(k in meta for k in merge_keys):
            sm = dict(spec.metadata or {})
            for k in merge_keys:
                if k in meta:
                    sm[k] = meta[k]
            spec = spec.model_copy(update={"metadata": sm})

        bhash = compute_backtest_hash(spec)
        force = bool(meta.get("force_recompute"))
        injected = (
            meta.get("targets_by_date") is not None
            or meta.get("target_positions") is not None
            or meta.get("price_bars") is not None
        )
        if not force and not injected:
            try:
                summary = self._registry.get_research_backtest(bhash)
                return BacktestResult(
                    backtest_hash=bhash,
                    frames=BacktestFrames(
                        backtest_hash=bhash, strategy_hash=strategy_hash
                    ),
                    summary=summary,
                    strategy=strategy,
                )
            except KeyError:
                pass

        targets = load_targets_by_date(
            self._store, strategy_hash, metadata=meta
        )
        if not targets:
            raise ResearchBacktestError(
                f"no target positions for strategy_hash={strategy_hash}"
            )

        instruments: set[str] = set()
        for rows in targets.values():
            for r in rows:
                k = str(r.get("instrument_key") or "")
                if k:
                    instruments.add(k)
        if spec.benchmark_mode == "INDEX" and spec.benchmark_instrument_key:
            instruments.add(spec.benchmark_instrument_key)

        # 价格窗口略放宽：信号日可能在 start 前一日
        price_start = min(targets.keys()) if targets else spec.start_date
        if price_start > spec.start_date:
            price_start = spec.start_date
        price_index = load_price_bars(
            self._store,
            instruments=instruments,
            start=price_start,
            end=spec.end_date,
            exchange=spec.exchange,
            metadata=meta,
        )
        if not price_index:
            raise ResearchBacktestError("no price bars for backtest window")

        frames = self._engine.run(
            spec,
            targets_by_signal_date=targets,
            price_index=price_index,
            metadata=meta,
        )
        summary = self._writer.write(spec, frames, force=force)
        return BacktestResult(
            backtest_hash=bhash,
            frames=frames,
            summary=summary,
            strategy=strategy,
        )

    def _resolve_strategy(
        self, strategy_hash: str, meta: dict[str, Any]
    ) -> StrategyResearchSummary | None:
        try:
            return self._registry.get_strategy_research(strategy_hash)
        except KeyError:
            if (
                meta.get("targets_by_date") is not None
                or meta.get("target_positions") is not None
            ):
                return None
            raise ResearchBacktestError(
                f"strategy_research not found: {strategy_hash}"
            ) from None


def _parse_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not hasattr(v, "hour"):
        return v
    return date.fromisoformat(str(v)[:10])
