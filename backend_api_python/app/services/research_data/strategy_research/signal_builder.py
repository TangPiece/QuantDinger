"""FactorDataset 面板 → Signal 行（PIT 时间）。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from app.services.research_data.contracts import Signal
from app.services.research_data.signal.timeutil import resolve_signal_times

from .protocol import SignalDefinition, StrategySpec


def _as_date(v: Any) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if hasattr(v, "date") and not isinstance(v, date):
        return v.date()
    return date.fromisoformat(str(v)[:10])


def _average_ranks(values: list[float]) -> list[float]:
    """平均秩（ties）。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _signal_id(strategy_hash: str, trading_date: str, instrument_key: str) -> str:
    raw = f"{strategy_hash}|{trading_date}|{instrument_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class FactorSignalBuilder:
    """从因子面板构建研究域 Signal。"""

    def build(
        self,
        factor_rows: list[dict[str, Any]],
        spec: StrategySpec,
        *,
        strategy_hash: str,
        factor_dataset_hash: str,
    ) -> list[Signal]:
        sig_def = spec.signal_definition or SignalDefinition(
            factor_dataset_id=spec.factor_dataset_id
        )
        field = sig_def.score_field or "value"
        by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for r in factor_rows:
            score = r.get(field, r.get("value", r.get("factor_value")))
            if score is None:
                continue
            try:
                fv = float(score)
            except (TypeError, ValueError):
                continue
            d = _as_date(r.get("trading_date") or r.get("factor_date"))
            by_date[d].append(
                {"instrument_key": str(r["instrument_key"]), "score": fv}
            )

        out: list[Signal] = []
        for d in sorted(by_date):
            day = by_date[d]
            # average-rank：分数越高秩越大；展示用「高分 → 小序号」= n+1-avg_rank
            avg_ranks = _average_ranks([x["score"] for x in day])
            n = len(day)
            day_str = d.isoformat()
            st, kt, et = resolve_signal_times(d)
            for i, item in enumerate(day):
                score = item["score"]
                # LONG_IF_POSITIVE：截面 Signal 一律 LONG（空头由 4I 持仓决定）
                if sig_def.direction_mode == "LONG_IF_POSITIVE":
                    direction = "LONG"
                elif score > 0:
                    direction = "LONG"
                elif score < 0:
                    direction = "SHORT"
                else:
                    direction = "FLAT"
                ik = item["instrument_key"]
                display_rank = int(round(n + 1.0 - avg_ranks[i]))
                out.append(
                    Signal(
                        signal_id=_signal_id(strategy_hash, day_str, ik),
                        instrument_key=ik,
                        trading_date=day_str,
                        direction=direction,  # type: ignore[arg-type]
                        score=float(score),
                        signal_time=st,
                        knowledge_time=kt,
                        execution_time=et,
                        rank=max(1, display_rank),
                        strategy_version=spec.strategy_version,
                        dataset_hash=factor_dataset_hash,
                    )
                )
        return out
