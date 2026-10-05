"""TargetPosition → OrderIntent 纯函数映射（不接 Broker / 不下单）。"""

from __future__ import annotations

from app.services.research_data.contracts import OrderIntent, TargetPosition


def order_intents_from_targets(
    positions: list[TargetPosition],
    *,
    notional: float = 1.0,
) -> list[OrderIntent]:
    """相对空仓：正权重 → BUY；quantity = weight * notional（占位，非真实股数）。

    本函数仅产出契约对象，禁止在此调用任何 broker / exchange API。
    """
    intents: list[OrderIntent] = []
    for p in positions:
        w = float(p.target_weight or 0.0)
        if w <= 0:
            continue
        qty = abs(w) * float(notional)
        intents.append(
            OrderIntent(
                instrument_key=p.instrument_key,
                side="BUY",
                quantity=qty,
                signal_id=p.signal_id,
                strategy_version=p.strategy_version,
                trading_date=p.trading_date,
            )
        )
    return intents
