"""4I positions → TargetPosition（挂到 strategy_hash）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from app.services.research_data.contracts import Signal, TargetPosition
from app.services.research_data.signal.timeutil import resolve_signal_times

from .protocol import StrategySpec


def _as_date_str(v: Any) -> str:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v.isoformat()
    text = str(v)[:10]
    return text


class PortfolioPositionBinder:
    """将 4I 持仓行映射为策略 TargetPosition。"""

    def bind(
        self,
        portfolio_positions: list[dict[str, Any]],
        spec: StrategySpec,
        *,
        strategy_hash: str,
        factor_dataset_hash: str,
        signals: list[Signal] | None = None,
    ) -> list[TargetPosition]:
        """portfolio_positions: 含 instrument_key, trading_date, target_weight|weight。"""
        sig_index: dict[tuple[str, str], str] = {}
        if signals:
            for s in signals:
                sig_index[(s.trading_date, s.instrument_key)] = s.signal_id

        pid = strategy_hash[:16]
        out: list[TargetPosition] = []
        for r in portfolio_positions:
            day = _as_date_str(r.get("trading_date") or r.get("factor_date"))
            ik = str(r["instrument_key"])
            w = r.get("target_weight", r.get("weight"))
            if w is None:
                continue
            st, _, _ = resolve_signal_times(day)
            ts = r.get("timestamp")
            if isinstance(ts, datetime):
                timestamp = ts
            else:
                timestamp = st
            out.append(
                TargetPosition(
                    instrument_key=ik,
                    trading_date=day,
                    portfolio_id=pid,
                    strategy_version=spec.strategy_version,
                    dataset_hash=factor_dataset_hash,
                    timestamp=timestamp,
                    target_weight=float(w),
                    signal_id=sig_index.get((day, ik)),
                )
            )
        return out
