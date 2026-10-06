"""BacktestFrames → R2 分区 + Registry Summary。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import ResearchBacktestSummary
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data import writer as rd_writer

from .artifact_store import BacktestArtifactStore
from .protocol import (
    ENGINE_VERSION,
    RETURN_CALCULATION_VERSION,
    BacktestFrames,
    BacktestManifest,
    BacktestSpec,
)


class BacktestDatasetWriter:
    """写 portfolio/returns/positions/turnover + Summary。"""

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

    def write(
        self,
        spec: BacktestSpec,
        frames: BacktestFrames,
        *,
        force: bool = False,
    ) -> ResearchBacktestSummary:
        bhash = frames.backtest_hash
        if not force:
            try:
                return self._registry.get_research_backtest(bhash)
            except (KeyError, AttributeError):
                pass

        version = spec.engine_version or ENGINE_VERSION
        checksums: list[str] = []
        checksums += self._write_nav(frames, version)
        checksums += self._write_returns(frames, version)
        checksums += self._write_positions(frames, version)
        checksums += self._write_turnover(frames, version)
        checksum = hashlib.sha256(
            "".join(checksums or ["empty"]).encode()
        ).hexdigest()

        summary = ResearchBacktestSummary(
            backtest_hash=bhash,
            strategy_hash=spec.strategy_hash,
            start_date=spec.start_date.isoformat(),
            end_date=spec.end_date.isoformat(),
            execution_policy=spec.execution_policy.mode,
            benchmark_mode=spec.benchmark_mode,
            benchmark_instrument_key=spec.benchmark_instrument_key or "",
            metrics_json=dict(frames.metrics or {}),
            benchmark_metrics_json=dict(frames.benchmark_metrics or {}),
            engine_version=version,
            return_calculation_version=(
                spec.return_calculation_version or RETURN_CALCULATION_VERSION
            ),
            metadata={
                "allows_same_close": spec.execution_policy.allows_same_close,
                **dict(frames.metadata or {}),
            },
        )
        man = BacktestManifest(
            backtest_hash=bhash,
            strategy_hash=spec.strategy_hash,
            start_date=spec.start_date.isoformat(),
            end_date=spec.end_date.isoformat(),
            execution_policy=spec.execution_policy.mode,
            allows_same_close=spec.execution_policy.allows_same_close,
            engine_version=version,
            return_calculation_version=spec.return_calculation_version,
            nav_rows=len(frames.nav),
            return_rows=len(frames.returns),
            position_rows=len(frames.positions),
            checksum=checksum,
            metadata=dict(frames.metadata or {}),
        )
        art = self._artifacts.write_manifest(
            man,
            summary=summary,
            metrics={
                "metrics": frames.metrics,
                "benchmark_metrics": frames.benchmark_metrics,
            },
        )
        summary = summary.model_copy(
            update={"storage_uri": art.storage_uri, "checksum": art.checksum}
        )
        self._registry.upsert_research_backtest(summary)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return summary

    def _write_nav(self, frames: BacktestFrames, version: str) -> list[str]:
        by_ym: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for p in frames.nav:
            by_ym[(p.trading_date.year, p.trading_date.month)].append(
                {
                    "trading_date": p.trading_date,
                    "nav": float(p.nav),
                    "cash": float(p.cash),
                    "gross_exposure": float(p.gross_exposure),
                    "data_version": version,
                }
            )
        return self._flush("portfolio", by_ym, frames.backtest_hash, version)

    def _write_returns(self, frames: BacktestFrames, version: str) -> list[str]:
        by_ym: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for r in frames.returns:
            by_ym[(r.trading_date.year, r.trading_date.month)].append(
                {
                    "trading_date": r.trading_date,
                    "portfolio_return": (
                        float(r.portfolio_return)
                        if r.portfolio_return is not None
                        else float("nan")
                    ),
                    "benchmark_return": (
                        float(r.benchmark_return)
                        if r.benchmark_return is not None
                        else float("nan")
                    ),
                    "excess_return": (
                        float(r.excess_return)
                        if r.excess_return is not None
                        else float("nan")
                    ),
                    "data_version": version,
                }
            )
        return self._flush("returns", by_ym, frames.backtest_hash, version)

    def _write_positions(self, frames: BacktestFrames, version: str) -> list[str]:
        by_ym: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for p in frames.positions:
            by_ym[(p.trading_date.year, p.trading_date.month)].append(
                {
                    "trading_date": p.trading_date,
                    "instrument_key": p.instrument_key,
                    "shares": float(p.shares),
                    "weight": float(p.weight),
                    "price": float(p.price),
                    "data_version": version,
                }
            )
        return self._flush("positions", by_ym, frames.backtest_hash, version)

    def _write_turnover(self, frames: BacktestFrames, version: str) -> list[str]:
        by_ym: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for t in frames.turnover:
            by_ym[(t.trading_date.year, t.trading_date.month)].append(
                {
                    "trading_date": t.trading_date,
                    "turnover": (
                        float(t.turnover)
                        if t.turnover is not None
                        else float("nan")
                    ),
                    "rebalanced": bool(t.rebalanced),
                    "data_version": version,
                }
            )
        return self._flush("turnover", by_ym, frames.backtest_hash, version)

    def _flush(
        self,
        kind: str,
        by_ym: dict[tuple[int, int], list[dict[str, Any]]],
        backtest_hash: str,
        version: str,
    ) -> list[str]:
        checksums: list[str] = []
        writers = {
            "portfolio": rd_writer.write_research_backtest_nav_panel,
            "returns": rd_writer.write_research_backtest_return_panel,
            "positions": rd_writer.write_research_backtest_position_panel,
            "turnover": rd_writer.write_research_backtest_turnover_panel,
        }
        write_fn = writers[kind]
        for (y, m), part in sorted(by_ym.items()):
            written = write_fn(
                self._store,
                part,
                backtest_hash=backtest_hash,
                year=y,
                month=m,
                version=version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
        return checksums
