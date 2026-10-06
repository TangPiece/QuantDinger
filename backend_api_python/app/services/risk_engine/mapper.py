"""PositionDelta → research OrderIntent。"""

from __future__ import annotations

from typing import Sequence

from app.services.research_data.contracts import OrderIntent

from .protocol import RiskDecision, RiskPolicy


def deltas_to_order_intents(
    deltas: Sequence,
    *,
    verdict: str,
    policy: RiskPolicy,
    trading_date: str = "",
    idempotency_key: str = "",
    strategy_version: str = "",
) -> list[OrderIntent]:
    """将通过风控的 delta 映射为 OrderIntent（无 Broker id）。"""
    if verdict in ("REJECT", "ERROR"):
        return []
    out: list[OrderIntent] = []
    for d in deltas:
        if str(getattr(d, "side", "FLAT")) == "FLAT":
            continue
        dq = float(getattr(d, "delta_quantity", 0.0) or 0.0)
        if abs(dq) < 1e-12:
            continue
        side = "BUY" if dq > 0 else "SELL"
        reason = (
            f"RISK_{verdict}|policy={policy.policy_code}@{policy.policy_version}"
            f"|idem={idempotency_key[:12]}"
        )
        out.append(
            OrderIntent(
                instrument_key=str(d.instrument_key),
                side=side,  # type: ignore[arg-type]
                quantity=abs(dq),
                trading_date=trading_date or None,
                strategy_version=strategy_version or None,
                target_quantity=float(getattr(d, "target_quantity", 0.0) or 0.0),
                current_quantity=float(getattr(d, "current_quantity", 0.0) or 0.0),
                quantity_delta=dq,
                reason=reason,
            )
        )
    return out


def decision_to_intents(
    decision: RiskDecision,
    *,
    policy: RiskPolicy,
    trading_date: str = "",
    idempotency_key: str = "",
) -> list[OrderIntent]:
    return deltas_to_order_intents(
        decision.adjusted_deltas,
        verdict=decision.verdict,
        policy=policy,
        trading_date=trading_date,
        idempotency_key=idempotency_key,
    )
