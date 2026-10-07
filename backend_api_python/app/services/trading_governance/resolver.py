"""Phase 7E：EffectiveCaps = min(scale, capital, capacity, env floor)。"""

from __future__ import annotations

import os

from .capital import remaining_notional
from .protocol import (
    CapacityLimit,
    CapitalAllocation,
    EffectiveCaps,
    ScaleLevel,
)
from .scale import scale_profile


def _env_hard_floor() -> dict[str, float | int]:
    """Controlled Live env 硬下限（与 7C config 对齐，只收紧不放宽）。"""

    def _f(name: str, default: float) -> float:
        raw = (os.environ.get(name) or "").strip()
        return float(raw) if raw else default

    def _i(name: str, default: int) -> int:
        raw = (os.environ.get(name) or "").strip()
        return int(raw) if raw else default

    return {
        "max_notional_per_order": _f("CONTROLLED_LIVE_MAX_NOTIONAL", 5000.0),
        "max_notional_session": _f(
            "CONTROLLED_LIVE_MAX_NOTIONAL_SESSION",
            _f("CONTROLLED_LIVE_MAX_NOTIONAL", 5000.0),
        ),
        "max_orders": _i("CONTROLLED_LIVE_MAX_ORDERS", 1),
    }


def resolve_effective_caps(
    *,
    account_id: str,
    strategy_id: str,
    scale_level: ScaleLevel,
    capital: CapitalAllocation | None = None,
    capacity: CapacityLimit | None = None,
    live_env_authorized: bool = False,
) -> EffectiveCaps:
    """合并各层上限；L4 且未 LIVE 授权时 environment 仍 LIVE_CONTROLLED。"""
    prof = scale_profile(scale_level)
    floor = _env_hard_floor()

    max_order = min(
        float(prof.get("max_notional_per_order", 0) or 0) or float("inf"),
        float(floor["max_notional_per_order"]) if floor["max_notional_per_order"] else float("inf"),
    )
    max_sess = min(
        float(prof.get("max_notional_session", 0) or 0) or float("inf"),
        float(floor["max_notional_session"]) if floor["max_notional_session"] else float("inf"),
    )
    max_orders = int(prof.get("max_orders", 0) or 0)
    if floor["max_orders"]:
        max_orders = min(max_orders, int(floor["max_orders"])) if max_orders else int(floor["max_orders"])

    if capital is not None:
        rem = remaining_notional(capital)
        max_order = min(max_order, rem) if max_order < float("inf") else rem
        max_sess = min(max_sess, rem) if max_sess < float("inf") else rem

    max_order_size = 0.0
    if capacity is not None:
        if capacity.max_notional > 0:
            max_order = min(max_order, capacity.max_notional) if max_order < float("inf") else capacity.max_notional
        if capacity.max_order_size > 0:
            max_order_size = capacity.max_order_size

    env = str(prof.get("environment") or "LIVE_CONTROLLED")
    if env == "LIVE" and not live_env_authorized:
        env = "LIVE_CONTROLLED"

    if max_order == float("inf"):
        max_order = 0.0
    if max_sess == float("inf"):
        max_sess = 0.0

    return EffectiveCaps(
        account_id=account_id,
        strategy_id=strategy_id,
        scale_level=scale_level,
        max_notional_per_order=max_order,
        max_notional_session=max_sess,
        max_orders=max_orders,
        max_order_size=max_order_size,
        environment=env,
        live_env_authorized=live_env_authorized,
    )
