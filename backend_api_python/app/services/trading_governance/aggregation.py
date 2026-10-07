"""Phase 7E：多策略 targets → 净 Portfolio Target。"""

from __future__ import annotations

from collections import defaultdict

from .protocol import PortfolioTarget, StrategyTarget


def aggregate_targets(
    account_id: str,
    strategy_targets: tuple[StrategyTarget, ...],
) -> list[PortfolioTarget]:
    """同 instrument 买卖相抵，输出净额与 attribution legs。"""
    buckets: dict[str, list[StrategyTarget]] = defaultdict(list)
    for t in strategy_targets:
        buckets[t.instrument_key].append(t)

    out: list[PortfolioTarget] = []
    for instrument_key, legs in buckets.items():
        signed = 0.0
        for leg in legs:
            q = float(leg.quantity)
            if leg.side == "SELL":
                q = -q
            signed += q
        if signed > 0:
            net_side = "BUY"
            net_q = signed
        elif signed < 0:
            net_side = "SELL"
            net_q = abs(signed)
        else:
            net_side = "FLAT"
            net_q = 0.0
        out.append(
            PortfolioTarget(
                account_id=account_id,
                instrument_key=instrument_key,
                net_side=net_side,
                net_quantity=net_q,
                legs=tuple(legs),
                metadata={"leg_count": len(legs)},
            )
        )
    return out
