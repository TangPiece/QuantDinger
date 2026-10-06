"""StrategyFrames → R2 signals/positions + Summary。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from app.services.research_data.canonical_store import CanonicalStore
from app.services.research_data.contracts import (
    ResearchStrategyRecord,
    StrategyResearchSummary,
)
from app.services.research_data.registry import ResearchRegistry
from app.services.research_data import writer as rd_writer

from .artifact_store import StrategyArtifactStore
from .protocol import (
    STRATEGY_VERSION,
    StrategyFrames,
    StrategyManifest,
    StrategySpec,
)


class StrategyDatasetWriter:
    """写 signals / target_positions + Registry。"""

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

    def write(
        self,
        spec: StrategySpec,
        frames: StrategyFrames,
        *,
        portfolio_summary_meta: dict[str, Any] | None = None,
        position_legs: dict[tuple[str, str], str] | None = None,
        force: bool = False,
    ) -> StrategyResearchSummary:
        shash = frames.strategy_hash
        if not force:
            try:
                return self._registry.get_strategy_research(shash)
            except (KeyError, AttributeError):
                pass

        checksums: list[str] = []
        checksums += self._write_signals(spec, frames)
        checksums += self._write_positions(spec, frames, position_legs or {})
        checksum = hashlib.sha256(
            "".join(checksums or ["empty"]).encode()
        ).hexdigest()

        meta = dict(portfolio_summary_meta or {})
        summary = StrategyResearchSummary(
            strategy_hash=shash,
            strategy_code=spec.strategy_code,
            strategy_version_label=spec.strategy_version or STRATEGY_VERSION,
            factor_dataset_id=spec.factor_dataset_id,
            portfolio_hash=spec.portfolio_hash,
            evaluation_hash=str(meta.get("evaluation_hash") or ""),
            signal_definition_json=(
                spec.signal_definition.model_dump(mode="json")
                if spec.signal_definition
                else {}
            ),
            rebalance_rule_json=spec.rebalance_rule.model_dump(mode="json"),
            holding_rule_json=spec.holding_rule.model_dump(mode="json"),
            universe_code=spec.universe_code,
            snapshot_id=spec.snapshot_id,
            signal_row_count=len(frames.signals),
            position_row_count=len(frames.positions),
            metadata={
                "portfolio_id": shash[:16],
                "timing_profile": spec.timing_profile,
            },
        )
        man = StrategyManifest(
            strategy_hash=shash,
            strategy_code=spec.strategy_code,
            factor_dataset_id=spec.factor_dataset_id,
            portfolio_hash=spec.portfolio_hash,
            strategy_spec=spec.model_dump(mode="json"),
            signal_rows=len(frames.signals),
            position_rows=len(frames.positions),
            checksum=checksum,
            strategy_version=spec.strategy_version,
        )
        art = self._artifacts.write_manifest(
            man,
            summary=summary,
            strategy_spec=spec.model_dump(mode="json"),
        )
        summary = summary.model_copy(
            update={"storage_uri": art.storage_uri, "checksum": art.checksum}
        )

        # 名录 + 版本
        self._registry.upsert_research_strategy(
            ResearchStrategyRecord(
                strategy_code=spec.strategy_code,
                name=spec.strategy_name or spec.strategy_code,
                status="ACTIVE",
                metadata={"latest_strategy_hash": shash},
            )
        )
        self._registry.upsert_strategy_research(summary)
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return summary

    def _write_signals(
        self, spec: StrategySpec, frames: StrategyFrames
    ) -> list[str]:
        by_ym: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for s in frames.signals:
            d = date_from_str(s.trading_date)
            by_ym[(d.year, d.month)].append(
                {
                    "signal_id": s.signal_id,
                    "instrument_key": s.instrument_key,
                    "trading_date": s.trading_date,
                    "direction": s.direction,
                    "score": float(s.score),
                    "signal_time": s.signal_time,
                    "knowledge_time": s.knowledge_time,
                    "execution_time": s.execution_time,
                    "rank": int(s.rank or 0),
                    "strategy_version": s.strategy_version,
                    "dataset_hash": s.dataset_hash,
                    "data_version": spec.strategy_version,
                }
            )
        checksums = []
        for (y, m), part in sorted(by_ym.items()):
            written = rd_writer.write_strategy_signal_panel(
                self._store,
                part,
                strategy_hash=frames.strategy_hash,
                year=y,
                month=m,
                version=spec.strategy_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
        return checksums

    def _write_positions(
        self,
        spec: StrategySpec,
        frames: StrategyFrames,
        legs: dict[tuple[str, str], str],
    ) -> list[str]:
        by_ym: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for p in frames.positions:
            d = date_from_str(p.trading_date)
            by_ym[(d.year, d.month)].append(
                {
                    "instrument_key": p.instrument_key,
                    "trading_date": p.trading_date,
                    "portfolio_id": p.portfolio_id,
                    "strategy_version": p.strategy_version,
                    "dataset_hash": p.dataset_hash,
                    "timestamp": p.timestamp,
                    "target_weight": (
                        float(p.target_weight)
                        if p.target_weight is not None
                        else float("nan")
                    ),
                    "signal_id": p.signal_id or "",
                    "leg": legs.get((p.trading_date, p.instrument_key), ""),
                    "data_version": spec.strategy_version,
                }
            )
        checksums = []
        for (y, m), part in sorted(by_ym.items()):
            written = rd_writer.write_strategy_target_position_panel(
                self._store,
                part,
                strategy_hash=frames.strategy_hash,
                year=y,
                month=m,
                version=spec.strategy_version,
                registry=self._registry,
            )
            checksums.append(written["checksum"])
        return checksums


def date_from_str(s: str):
    from datetime import date as date_cls

    return date_cls.fromisoformat(str(s)[:10])
