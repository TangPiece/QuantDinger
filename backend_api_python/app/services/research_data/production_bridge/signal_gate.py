"""Production Signal Gate（基础风控；不停在账户级）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from app.services.research_data.contracts import Signal, TargetPosition

from .protocol import GateResult


def run_signal_gate(
    signals: Sequence[Signal],
    targets: Sequence[TargetPosition],
    *,
    universe_membership: Sequence[str] | None = None,
    max_single_weight: float = 0.2,
    max_gross_exposure: float = 1.0,
    max_turnover: float | None = None,
    prev_weights: Mapping[str, float] | None = None,
    stale_after_hours: float = 48.0,
    now: datetime | None = None,
) -> GateResult:
    """Signal / TargetPosition 基础校验；失败则 STOP。"""
    details: dict[str, Any] = {
        "n_signals": len(signals),
        "n_targets": len(targets),
    }
    failures: list[str] = []
    membership = {str(x) for x in (universe_membership or [])}
    now = now or datetime.now(timezone.utc)

    for s in signals:
        if membership and s.instrument_key not in membership:
            failures.append(f"signal_outside_universe:{s.instrument_key}")
        # stale
        kt = s.knowledge_time
        if kt.tzinfo is None:
            kt = kt.replace(tzinfo=timezone.utc)
        if now - kt > timedelta(hours=stale_after_hours):
            failures.append(f"stale_signal:{s.instrument_key}")
            break

    gross = 0.0
    for t in targets:
        w = float(t.target_weight or 0.0)
        if abs(w) > max_single_weight + 1e-12:
            failures.append(
                f"max_single_weight:{t.instrument_key}={w}>{max_single_weight}"
            )
        gross += abs(w)
        if membership and t.instrument_key not in membership:
            failures.append(f"target_outside_universe:{t.instrument_key}")
    details["gross_exposure"] = gross
    if gross > max_gross_exposure + 1e-12:
        failures.append(f"max_gross_exposure:{gross}>{max_gross_exposure}")

    if max_turnover is not None and prev_weights is not None:
        cur = {t.instrument_key: float(t.target_weight or 0.0) for t in targets}
        keys = set(cur) | set(prev_weights)
        turnover = 0.5 * sum(
            abs(cur.get(k, 0.0) - float(prev_weights.get(k, 0.0))) for k in keys
        )
        details["turnover"] = turnover
        if turnover > max_turnover + 1e-12:
            failures.append(f"max_turnover:{turnover}>{max_turnover}")

    if failures:
        return GateResult(
            gate="signal",
            passed=False,
            severity="P0",
            message="; ".join(failures[:8]),
            details=details,
        )
    return GateResult(
        gate="signal",
        passed=True,
        message="signal gate ok",
        details=details,
    )
