"""停牌 / 涨跌停 / 可买可卖 → ExecutionDecision。"""

from __future__ import annotations

from typing import Literal

from app.services.research_data.backtest.policy import TradingRule

from .lot import adjust_lot_quantity
from .models import (
    REASON_HOLD,
    REASON_LIMIT_DOWN,
    REASON_LIMIT_UP,
    REASON_LOT_SIZE_FLOOR,
    REASON_LOT_SIZE_REJECT,
    REASON_NO_PRICE,
    REASON_OK,
    REASON_SHORT_NOT_ALLOWED,
    REASON_SUSPENDED,
    REASON_T_PLUS,
    EligibilityFlags,
    ExecutionDecision,
    MarketBar,
)


class SuspensionFailError(RuntimeError):
    """suspension_mode=fail 时抛出。"""


def build_eligibility(bar: MarketBar, rule: TradingRule) -> EligibilityFlags:
    """根据 bar 与规则计算可买可卖。"""
    suspended = bool(bar.is_suspended)
    limit_up = bool(bar.is_limit_up)
    limit_down = bool(bar.is_limit_down)
    if rule.limit_up_down:
        # 若未显式标记，可用价格触及涨跌停价推断
        if bar.upper_limit is not None and bar.close is not None:
            if abs(float(bar.close) - float(bar.upper_limit)) <= 1e-9 or (
                bar.open is not None and abs(float(bar.open) - float(bar.upper_limit)) <= 1e-9
            ):
                limit_up = True
        if bar.lower_limit is not None and bar.close is not None:
            if abs(float(bar.close) - float(bar.lower_limit)) <= 1e-9 or (
                bar.open is not None and abs(float(bar.open) - float(bar.lower_limit)) <= 1e-9
            ):
                limit_down = True
    else:
        limit_up = False
        limit_down = False

    buy_ok = (not suspended) and (not limit_up)
    sell_ok = (not suspended) and (not limit_down)
    return EligibilityFlags(
        is_suspended=suspended,
        is_limit_up=limit_up,
        is_limit_down=limit_down,
        buy_ok=buy_ok,
        sell_ok=sell_ok,
    )


def decide_execution(
    *,
    instrument_key: str,
    side: Literal["BUY", "SELL"],
    quantity: float,
    bar: MarketBar | None,
    rule: TradingRule,
    sellable_quantity: float | None = None,
    fill_price: float | None = None,
) -> ExecutionDecision:
    """综合停牌/涨跌停/整手/可卖库存，产出 ExecutionDecision。

    Args:
        sellable_quantity: T+1 下当日可卖数量；None 表示不限制库存（仅 short_allowed）
        fill_price: 预估成交价（缺失则 NO_PRICE）
    """
    req = abs(float(quantity))
    empty = ExecutionDecision(
        instrument_key=instrument_key,
        side=side,
        executable=False,
        requested_quantity=req,
        executable_quantity=0.0,
        rejected_quantity=req,
    )
    if req <= 0:
        return empty.model_copy(update={"reason": REASON_OK, "rejected_quantity": 0.0})

    if bar is None:
        return empty.model_copy(update={"reason": REASON_NO_PRICE})

    flags = build_eligibility(bar, rule)

    if flags.is_suspended:
        if rule.suspension_mode == "fail":
            raise SuspensionFailError(f"suspended: {instrument_key} on {bar.trading_date}")
        if rule.suspension_mode == "hold":
            return empty.model_copy(
                update={"reason": REASON_HOLD, "eligibility": flags}
            )
        return empty.model_copy(
            update={"reason": REASON_SUSPENDED, "eligibility": flags}
        )

    if side == "BUY" and not flags.buy_ok:
        return empty.model_copy(
            update={"reason": REASON_LIMIT_UP, "eligibility": flags}
        )
    if side == "SELL" and not flags.sell_ok:
        return empty.model_copy(
            update={"reason": REASON_LIMIT_DOWN, "eligibility": flags}
        )

    price = fill_price
    if price is None:
        return empty.model_copy(
            update={"reason": REASON_NO_PRICE, "eligibility": flags}
        )

    # 整手
    lot_res = adjust_lot_quantity(req, rule)
    exec_qty = lot_res.executable_quantity
    rejected = lot_res.rejected_quantity
    reason = lot_res.reason if lot_res.reason != REASON_OK else REASON_OK

    if exec_qty <= 0:
        return ExecutionDecision(
            instrument_key=instrument_key,
            side=side,
            executable=False,
            reason=reason if reason != REASON_OK else REASON_LOT_SIZE_REJECT,
            requested_quantity=req,
            executable_quantity=0.0,
            rejected_quantity=req,
            eligibility=flags,
            fill_price=price,
        )

    # 可卖库存 / 禁止卖空
    if side == "SELL":
        if sellable_quantity is not None:
            sellable = max(0.0, float(sellable_quantity))
            if exec_qty > sellable + 1e-12:
                clipped = sellable
                # 再套整手
                lot2 = adjust_lot_quantity(clipped, rule)
                rejected += exec_qty - lot2.executable_quantity
                exec_qty = lot2.executable_quantity
                if exec_qty <= 0:
                    # 区分 T+1 与卖空
                    why = REASON_T_PLUS if sellable < req else REASON_SHORT_NOT_ALLOWED
                    return ExecutionDecision(
                        instrument_key=instrument_key,
                        side=side,
                        executable=False,
                        reason=why,
                        requested_quantity=req,
                        executable_quantity=0.0,
                        rejected_quantity=req,
                        eligibility=flags,
                        fill_price=price,
                    )
                reason = REASON_T_PLUS
        elif not rule.short_allowed:
            # 无持仓信息且禁止卖空：由调用方保证；此处不额外拦截
            pass

    partial = rejected > 1e-12
    return ExecutionDecision(
        instrument_key=instrument_key,
        side=side,
        executable=exec_qty > 0,
        reason=reason
        if reason in (REASON_LOT_SIZE_FLOOR, REASON_LOT_SIZE_REJECT, REASON_T_PLUS)
        else REASON_OK,
        requested_quantity=req,
        executable_quantity=exec_qty,
        rejected_quantity=rejected if partial or reason != REASON_OK else 0.0,
        eligibility=flags,
        fill_price=price,
    )
