"""PortfolioFrames → R2 明细 + D1/Local Summary。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import FactorPortfolioSummary
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data import writer as rd_writer

from .artifact_store import PortfolioArtifactStore
from .protocol import (
    PORTFOLIO_VERSION,
    PortfolioFrames,
    PortfolioManifest,
    PortfolioSpec,
)


class PortfolioDatasetWriter:
    """写 positions/weights/returns/turnover + Summary。"""

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

    def write(
        self,
        spec: PortfolioSpec,
        frames: PortfolioFrames,
        *,
        factor_dataset_hash: str,
        force: bool = False,
    ) -> FactorPortfolioSummary:
        phash = frames.portfolio_hash
        if not force:
            try:
                return self._registry.get_factor_portfolio(phash)
            except (KeyError, AttributeError):
                pass

        checksums: list[str] = []
        checksums += self._write_positions(spec, frames, factor_dataset_hash)
        checksums += self._write_weights(spec, frames)
        checksums += self._write_returns(spec, frames)
        checksums += self._write_turnover(spec, frames)
        checksum = hashlib.sha256(
            "".join(checksums or ["empty"]).encode()
        ).hexdigest()

        selection = {
            "selection_mode": spec.selection_mode,
            "top_n": spec.top_n,
            "top_pct": spec.top_pct,
            "group_count": spec.group_count,
            "horizon": spec.horizon,
            "min_turnover": spec.min_turnover,
            "direction": spec.direction,
        }
        summary = FactorPortfolioSummary(
            portfolio_hash=phash,
            factor_dataset_id=spec.factor_dataset_id,
            evaluation_hash=spec.evaluation_hash,
            construction_method=spec.construction_method,
            weight_method=spec.weight_method,
            rebalance_frequency=spec.rebalance_frequency,
            selection_json=selection,
            metrics_json=dict(frames.metrics or {}),
            portfolio_version=spec.portfolio_version or PORTFOLIO_VERSION,
            metadata={
                "factor_dataset_hash": factor_dataset_hash,
                "portfolio_id": phash[:16],
            },
        )
        man = PortfolioManifest(
            portfolio_hash=phash,
            factor_dataset_id=spec.factor_dataset_id,
            evaluation_hash=spec.evaluation_hash,
            portfolio_spec=spec.model_dump(mode="json"),
            position_rows=len(frames.positions),
            return_rows=len(frames.returns),
            checksum=checksum,
            portfolio_version=spec.portfolio_version,
        )
        art = self._artifacts.write_manifest(
            man, summary=summary, metrics=frames.metrics
        )
        summary = summary.model_copy(
            update={"storage_uri": art.storage_uri, "checksum": art.checksum}
        )
        self._registry.upsert_factor_portfolio(summary)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return summary

    def _write_positions(
        self,
        spec: PortfolioSpec,
        frames: PortfolioFrames,
        factor_dataset_hash: str,
    ) -> list[str]:
        pid = frames.portfolio_hash[:16]
        by_ym: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for p in frames.positions:
            ts = datetime(
                p.trading_date.year,
                p.trading_date.month,
                p.trading_date.day,
                12,
                0,
                0,
                tzinfo=timezone.utc,
            )
            by_ym[(p.trading_date.year, p.trading_date.month)].append(
                {
                    "instrument_key": p.instrument_key,
                    "trading_date": p.trading_date.isoformat(),
                    "portfolio_id": pid,
                    "strategy_version": spec.portfolio_version,
                    "dataset_hash": factor_dataset_hash,
                    "timestamp": ts,
                    "target_weight": float(p.weight),
                    "leg": p.leg,
                    "data_version": spec.portfolio_version,
                }
            )
        checksums = []
        for (y, m), part in sorted(by_ym.items()):
            written = rd_writer.write_portfolio_position_panel(
                self._store,
                part,
                portfolio_hash=frames.portfolio_hash,
                year=y,
                month=m,
                version=spec.portfolio_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
        return checksums

    def _write_weights(
        self, spec: PortfolioSpec, frames: PortfolioFrames
    ) -> list[str]:
        by_ym: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for p in frames.positions:
            by_ym[(p.trading_date.year, p.trading_date.month)].append(
                {
                    "trading_date": p.trading_date,
                    "instrument_key": p.instrument_key,
                    "weight": float(p.weight),
                    "leg": p.leg,
                    "factor_value": (
                        float(p.factor_value)
                        if p.factor_value is not None
                        else float("nan")
                    ),
                    "data_version": spec.portfolio_version,
                }
            )
        checksums = []
        for (y, m), part in sorted(by_ym.items()):
            written = rd_writer.write_portfolio_weight_panel(
                self._store,
                part,
                portfolio_hash=frames.portfolio_hash,
                year=y,
                month=m,
                version=spec.portfolio_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
        return checksums

    def _write_returns(
        self, spec: PortfolioSpec, frames: PortfolioFrames
    ) -> list[str]:
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
                    "long_return": (
                        float(r.long_return)
                        if r.long_return is not None
                        else float("nan")
                    ),
                    "short_return": (
                        float(r.short_return)
                        if r.short_return is not None
                        else float("nan")
                    ),
                    "long_short_return": (
                        float(r.long_short_return)
                        if r.long_short_return is not None
                        else float("nan")
                    ),
                    "sample_count": int(r.sample_count),
                    "data_version": spec.portfolio_version,
                }
            )
        checksums = []
        for (y, m), part in sorted(by_ym.items()):
            written = rd_writer.write_portfolio_return_panel(
                self._store,
                part,
                portfolio_hash=frames.portfolio_hash,
                year=y,
                month=m,
                version=spec.portfolio_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
        return checksums

    def _write_turnover(
        self, spec: PortfolioSpec, frames: PortfolioFrames
    ) -> list[str]:
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
                    "data_version": spec.portfolio_version,
                }
            )
        checksums = []
        for (y, m), part in sorted(by_ym.items()):
            written = rd_writer.write_portfolio_turnover_panel(
                self._store,
                part,
                portfolio_hash=frames.portfolio_hash,
                year=y,
                month=m,
                version=spec.portfolio_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
        return checksums
