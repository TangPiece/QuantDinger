"""SignalPipeline：Prediction → Signal → TargetPosition（默认不生成订单）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.research_data.contracts import (
    PredictionRecord,
    Signal,
    SignalRunRecord,
    TargetPosition,
)
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import SignalArtifactStore, compute_signal_artifact_id
from .predictions import normalize_predictions, prediction_fingerprint
from .specs import SignalRunSpec
from .version import SIGNAL_PIPELINE_VERSION


@dataclass
class SignalPipelineResult:
    """Signal 管线产物摘要。"""

    artifact_id: str
    strategy_version: str
    prediction_fingerprint: str
    signals: list[Signal] = field(default_factory=list)
    positions: list[TargetPosition] = field(default_factory=list)
    cash_weight: float = 0.0
    artifact_uri: str = ""
    signal_run_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class SignalPipeline:
    """组合 Strategy + Portfolio + ArtifactStore + Registry。"""

    def __init__(
        self,
        registry: ResearchRegistry,
        *,
        artifact_store: SignalArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._store = artifact_store or SignalArtifactStore()

    def run(
        self,
        predictions: list[PredictionRecord],
        spec: SignalRunSpec,
        *,
        snapshot_id: str | None = None,
        emit_order_intents: bool = False,
    ) -> SignalPipelineResult:
        """运行管线。emit_order_intents 默认 False（不下单、不调 mapper）。"""
        if emit_order_intents:
            # 显式拒绝在 pipeline 内接订单，避免误用
            raise ValueError(
                "SignalPipeline does not emit OrderIntent; "
                "use order_intents_from_targets() separately (contract only)"
            )

        preds = normalize_predictions(predictions, snapshot_id=snapshot_id)
        if not preds:
            raise ValueError("predictions must be non-empty")

        fp = prediction_fingerprint(preds)
        strategy = spec.strategy
        portfolio = spec.portfolio
        strategy_digest = strategy.strategy_digest()
        portfolio_digest = portfolio.portfolio_digest()
        artifact_id = compute_signal_artifact_id(
            prediction_fingerprint=fp,
            strategy_digest=strategy_digest,
            portfolio_digest=portfolio_digest,
        )
        portfolio_id = f"pf_{artifact_id[:16]}"

        signals = strategy.generate(preds)
        # 校验时间语义
        for s in signals:
            if s.execution_time <= s.signal_time:
                raise ValueError(
                    f"execution_time must be after signal_time for {s.signal_id}"
                )
            if s.knowledge_time != s.signal_time:
                # 日频收盘策略：knowledge == signal；若偏离则拒绝（防未来函数）
                raise ValueError(
                    f"knowledge_time must equal signal_time for day-close policy "
                    f"({s.signal_id})"
                )

        positions, cash_weight = portfolio.build(
            signals, portfolio_id=portfolio_id
        )
        # 校验权重：按交易日股票权重 + cash == 1
        by_day: dict[str, float] = {}
        for p in positions:
            by_day[p.trading_date] = by_day.get(p.trading_date, 0.0) + float(
                p.target_weight or 0.0
            )
        for day, gross in by_day.items():
            total = gross + cash_weight
            if abs(total - 1.0) > 1e-9:
                raise ValueError(
                    f"weights + cash must sum to 1 on {day}: got {total}"
                )

        # 回写 LONG 信号的 target_weight（便于追溯）
        weight_by_signal = {
            p.signal_id: p.target_weight for p in positions if p.signal_id
        }
        enriched: list[Signal] = []
        for s in signals:
            if s.signal_id in weight_by_signal:
                enriched.append(
                    s.model_copy(
                        update={"target_weight": weight_by_signal[s.signal_id]}
                    )
                )
            else:
                enriched.append(s)

        metadata: dict[str, Any] = {
            "artifact_id": artifact_id,
            "signal_pipeline_version": SIGNAL_PIPELINE_VERSION,
            "strategy_version": strategy.strategy_version,
            "strategy_digest": strategy_digest,
            "portfolio_code": portfolio.portfolio_code,
            "portfolio_digest": portfolio_digest,
            "prediction_fingerprint": fp,
            "time_policy": spec.time_policy,
            "cash_weight": cash_weight,
            "n_predictions": len(preds),
            "n_signals": len(enriched),
            "n_positions": len(positions),
            "snapshot_id": snapshot_id or (preds[0].snapshot_id if preds else ""),
            "dataset_hash": preds[0].dataset_hash,
            "model_version": preds[0].model_version,
        }

        artifact_uri = ""
        signal_run_id = artifact_id
        if spec.persist:
            art = self._store.write_bundle(
                artifact_id,
                signals=enriched,
                positions=positions,
                metadata=metadata,
            )
            artifact_uri = art.storage_uri
            self._registry.upsert_artifact(art)
            self._registry.upsert_signal_run(
                SignalRunRecord(
                    signal_run_id=signal_run_id,
                    strategy_version=strategy.strategy_version,
                    prediction_fingerprint=fp,
                    artifact_id=artifact_id,
                    storage_uri=artifact_uri,
                    cash_weight=cash_weight,
                    metadata=metadata,
                )
            )

        return SignalPipelineResult(
            artifact_id=artifact_id,
            strategy_version=strategy.strategy_version,
            prediction_fingerprint=fp,
            signals=enriched,
            positions=positions,
            cash_weight=cash_weight,
            artifact_uri=artifact_uri,
            signal_run_id=signal_run_id,
            metadata=metadata,
        )
