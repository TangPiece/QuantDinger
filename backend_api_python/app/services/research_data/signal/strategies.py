"""Signal Strategy：Prediction → Signal（与 Model 解耦）。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Protocol

from app.services.research_data.contracts import PredictionRecord, Signal
from app.services.research_data.hashing import canonical_json

from .timeutil import resolve_signal_times


def compute_signal_id(
    *,
    strategy_version: str,
    instrument_key: str,
    trading_date: str,
    dataset_hash: str,
) -> str:
    """单条 Signal 确定性 id。"""
    payload = "|".join(
        [
            str(strategy_version),
            str(instrument_key),
            str(trading_date),
            str(dataset_hash),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SignalStrategy(Protocol):
    """可插拔信号策略协议。"""

    @property
    def strategy_version(self) -> str: ...

    def strategy_digest(self) -> str: ...

    def generate(self, predictions: list[PredictionRecord]) -> list[Signal]: ...


def _group_by_date(
    predictions: list[PredictionRecord],
) -> dict[str, list[PredictionRecord]]:
    groups: dict[str, list[PredictionRecord]] = {}
    for p in predictions:
        groups.setdefault(p.trading_date, []).append(p)
    return groups


def _to_signal(
    pred: PredictionRecord,
    *,
    strategy_version: str,
    direction: Literal["LONG", "SHORT", "FLAT"],
    rank: int | None,
) -> Signal:
    signal_time, knowledge_time, execution_time = resolve_signal_times(
        pred.trading_date
    )
    return Signal(
        signal_id=compute_signal_id(
            strategy_version=strategy_version,
            instrument_key=pred.instrument_key,
            trading_date=pred.trading_date,
            dataset_hash=pred.dataset_hash,
        ),
        instrument_key=pred.instrument_key,
        trading_date=pred.trading_date,
        direction=direction,
        score=float(pred.prediction),
        signal_time=signal_time,
        knowledge_time=knowledge_time,
        execution_time=execution_time,
        rank=rank,
        model_version=pred.model_version,
        strategy_version=strategy_version,
        dataset_hash=pred.dataset_hash,
        bundle_hash=pred.bundle_hash,
    )


@dataclass(frozen=True)
class TopKStrategy:
    """按交易日截面取预测值 Top-K 为 LONG，其余 FLAT。"""

    k: int = 3
    long_only: bool = True
    code: str = "topk"
    version: str = "1"

    @property
    def strategy_version(self) -> str:
        return f"{self.code}@{self.version}"

    def strategy_digest(self) -> str:
        payload = {
            "code": self.code,
            "version": self.version,
            "k": self.k,
            "long_only": self.long_only,
        }
        return hashlib.sha256(
            canonical_json(payload).encode("utf-8")
        ).hexdigest()

    def generate(self, predictions: list[PredictionRecord]) -> list[Signal]:
        if self.k < 1:
            raise ValueError("TopKStrategy.k must be >= 1")
        out: list[Signal] = []
        for _day, rows in sorted(_group_by_date(predictions).items()):
            ranked = sorted(
                rows,
                key=lambda r: (-float(r.prediction), r.instrument_key),
            )
            long_set = {r.instrument_key for r in ranked[: self.k]}
            for i, r in enumerate(ranked, start=1):
                if r.instrument_key in long_set:
                    direction: Literal["LONG", "SHORT", "FLAT"] = "LONG"
                else:
                    direction = "FLAT"
                out.append(
                    _to_signal(
                        r,
                        strategy_version=self.strategy_version,
                        direction=direction,
                        rank=i,
                    )
                )
        return out


@dataclass(frozen=True)
class ThresholdStrategy:
    """预测值 >= min_score → LONG，否则 FLAT（可选 SHORT）。"""

    min_score: float = 0.0
    direction_mode: Literal["long_flat", "long_short"] = "long_flat"
    code: str = "threshold"
    version: str = "1"

    @property
    def strategy_version(self) -> str:
        return f"{self.code}@{self.version}"

    def strategy_digest(self) -> str:
        payload = {
            "code": self.code,
            "version": self.version,
            "min_score": self.min_score,
            "direction_mode": self.direction_mode,
        }
        return hashlib.sha256(
            canonical_json(payload).encode("utf-8")
        ).hexdigest()

    def generate(self, predictions: list[PredictionRecord]) -> list[Signal]:
        out: list[Signal] = []
        for _day, rows in sorted(_group_by_date(predictions).items()):
            ranked = sorted(
                rows,
                key=lambda r: (-float(r.prediction), r.instrument_key),
            )
            for i, r in enumerate(ranked, start=1):
                score = float(r.prediction)
                if score >= self.min_score:
                    direction: Literal["LONG", "SHORT", "FLAT"] = "LONG"
                elif self.direction_mode == "long_short":
                    direction = "SHORT"
                else:
                    direction = "FLAT"
                out.append(
                    _to_signal(
                        r,
                        strategy_version=self.strategy_version,
                        direction=direction,
                        rank=i,
                    )
                )
        return out
