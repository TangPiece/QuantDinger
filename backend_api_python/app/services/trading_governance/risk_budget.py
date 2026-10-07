"""Phase 7E：Account→Portfolio→Strategy→Order 四层风险预算叠加（min caps）。"""

from __future__ import annotations

from .protocol import OrderRiskContext, RiskBudgetLayer, RiskBudgetLayers


class RiskBudgetReject(RuntimeError):
    """任一层超限 REJECT。"""


def min_layer_caps(layers: tuple[RiskBudgetLayer, ...]) -> tuple[float, float, int]:
    """返回 (max_notional, max_exposure, max_orders) 的逐层 min。"""
    if not layers:
        return float("inf"), float("inf"), 0
    max_n = min(
        (l.max_notional if l.max_notional > 0 else l.max_exposure for l in layers),
        default=float("inf"),
    )
    max_exp = min((l.max_exposure for l in layers), default=float("inf"))
    orders = [l.max_orders for l in layers if l.max_orders > 0]
    max_o = min(orders) if orders else 0
    return max_n, max_exp, max_o


def check_order_layers(
    layers: RiskBudgetLayers,
    ctx: OrderRiskContext,
    *,
    session_notional_used: float = 0.0,
    order_count: int = 0,
) -> tuple[bool, str]:
    """校验单笔 + session 累计是否越界（取各层 min）。"""
    relevant: list[RiskBudgetLayer] = []
    for layer in layers.layers:
        if layer.scope == "ACCOUNT" and layer.scope_id == ctx.account_id:
            relevant.append(layer)
        elif layer.scope == "PORTFOLIO" and layer.scope_id == (ctx.portfolio_id or ctx.account_id):
            relevant.append(layer)
        elif layer.scope == "STRATEGY" and layer.scope_id == ctx.strategy_id:
            relevant.append(layer)
        elif layer.scope == "ORDER" and layer.scope_id == ctx.strategy_id:
            relevant.append(layer)

    max_n, max_exp, max_o = min_layer_caps(tuple(relevant))
    notional = float(ctx.notional)
    if notional <= 0:
        return False, "notional_must_be_positive"
    if max_n < float("inf") and notional > max_n:
        return False, "order_max_notional"
    if max_exp < float("inf") and session_notional_used + notional > max_exp:
        return False, "layer_max_exposure"
    if max_o > 0 and order_count >= max_o:
        return False, "layer_max_orders"
    return True, ""
