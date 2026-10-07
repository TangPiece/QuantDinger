"""Phase 7E：持仓按 strategy_id 归因（qty 之和应等于账户总量）。"""

from __future__ import annotations

from typing import Mapping, Sequence

from .protocol import AttributionRow


def attribute_positions_from_legs(
    account_id: str,
    legs: Sequence[Mapping[str, object]],
    *,
    prices: Mapping[str, float] | None = None,
) -> list[AttributionRow]:
    """从带 strategy_id 的 leg 列表分解 qty/notional。"""
    px = dict(prices or {})
    rows: dict[tuple[str, str], AttributionRow] = {}
    for leg in legs:
        sid = str(leg.get("strategy_id") or "")
        ik = str(leg.get("instrument_key") or "")
        qty = float(leg.get("quantity") or 0)
        side = str(leg.get("side") or "BUY").upper()
        if side == "SELL":
            qty = -qty
        key = (sid, ik)
        price = float(px.get(ik, leg.get("price") or 0) or 0)
        if key not in rows:
            rows[key] = AttributionRow(
                account_id=account_id,
                strategy_id=sid,
                instrument_key=ik,
            )
        row = rows[key]
        new_qty = row.quantity + qty
        rows[key] = row.model_copy(
            update={
                "quantity": new_qty,
                "notional": abs(new_qty) * price,
            }
        )
    return list(rows.values())


def assert_attribution_sums(
    rows: Sequence[AttributionRow],
    *,
    account_total_qty: Mapping[str, float],
) -> None:
    """校验各 instrument 归因 qty 之和等于账户总量。"""
    from collections import defaultdict

    summed: dict[str, float] = defaultdict(float)
    for r in rows:
        summed[r.instrument_key] += r.quantity
    for ik, total in account_total_qty.items():
        if abs(summed.get(ik, 0.0) - float(total)) > 1e-6:
            raise ValueError(
                f"attribution mismatch on {ik}: {summed.get(ik, 0)} vs account {total}"
            )
