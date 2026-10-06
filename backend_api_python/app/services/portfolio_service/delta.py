"""TargetPosition + Current → PositionDelta。"""

from __future__ import annotations

from typing import Mapping, Sequence

from app.services.research_data.contracts import TargetPosition

from .protocol import Position, PositionDelta


def compute_position_deltas(
    targets: Sequence[TargetPosition],
    positions: Mapping[str, Position],
    *,
    equity: float,
    prices: Mapping[str, float] | None = None,
) -> list[PositionDelta]:
    """由目标权重/数量与当前持仓计算差额。

    优先使用 target_quantity；否则用 target_weight * equity / price。
    """
    px = dict(prices or {})
    eq = max(float(equity), 0.0)
    # 当前权重
    gross = sum(max(float(p.market_value), 0.0) for p in positions.values()) or eq
    current_w: dict[str, float] = {}
    current_q: dict[str, float] = {}
    for k, p in positions.items():
        current_q[k] = float(p.quantity)
        if float(p.market_value):
            current_w[k] = float(p.market_value) / gross if gross else 0.0
        elif k in px and px[k] > 0 and eq > 0:
            current_w[k] = (float(p.quantity) * px[k]) / eq
        else:
            current_w[k] = 0.0

    target_keys = {str(t.instrument_key) for t in targets}
    deltas: list[PositionDelta] = []

    for t in targets:
        key = str(t.instrument_key)
        tw = float(t.target_weight) if t.target_weight is not None else None
        tq = float(t.target_quantity) if t.target_quantity is not None else None
        cq = float(current_q.get(key, 0.0))
        cw = float(current_w.get(key, 0.0))

        if tq is not None:
            target_qty = tq
            target_w = (tq * px[key] / eq) if (key in px and px[key] > 0 and eq > 0) else (tw or 0.0)
        elif tw is not None:
            target_w = tw
            if key in px and px[key] > 0 and eq > 0:
                target_qty = (tw * eq) / px[key]
            else:
                target_qty = cq  # 无价格时无法换算数量
        else:
            continue

        dq = target_qty - cq
        dw = target_w - cw
        if abs(dq) < 1e-9 and abs(dw) < 1e-12:
            side = "FLAT"
        elif dq > 0 or (abs(dq) < 1e-9 and dw > 0):
            side = "BUY"
        else:
            side = "SELL"
        notional = abs(dq) * float(px.get(key) or 0.0)
        deltas.append(
            PositionDelta(
                instrument_key=key,
                current_weight=cw,
                target_weight=float(target_w),
                delta_weight=dw,
                current_quantity=cq,
                target_quantity=float(target_qty),
                delta_quantity=dq,
                side=side,  # type: ignore[arg-type]
                notional=notional,
            )
        )

    # 目标未覆盖但当前有仓 → 清仓 delta
    for key, cq in current_q.items():
        if key in target_keys or abs(cq) < 1e-12:
            continue
        cw = float(current_w.get(key, 0.0))
        deltas.append(
            PositionDelta(
                instrument_key=key,
                current_weight=cw,
                target_weight=0.0,
                delta_weight=-cw,
                current_quantity=cq,
                target_quantity=0.0,
                delta_quantity=-cq,
                side="SELL",
                notional=abs(cq) * float(px.get(key) or 0.0),
            )
        )
    return deltas
