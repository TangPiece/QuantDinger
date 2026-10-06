"""Position / Cash Reducer：Event → State。"""

from __future__ import annotations

from typing import Sequence

from .protocol import Account, CashBalance, Position, PortfolioState, PositionEvent


class ReducerError(ValueError):
    """非法事件导致状态无法归约。"""


def _get_pos(state: PortfolioState, instrument_key: str) -> Position:
    pos = state.positions.get(instrument_key)
    if pos is None:
        return Position(instrument_key=instrument_key)
    return pos


def _put_pos(state: PortfolioState, pos: Position) -> None:
    if abs(float(pos.quantity)) < 1e-12 and abs(float(pos.frozen_quantity)) < 1e-12:
        state.positions.pop(pos.instrument_key, None)
    else:
        state.positions[pos.instrument_key] = pos


def apply_event(state: PortfolioState, event: PositionEvent) -> PortfolioState:
    """将单条事件归约到 PortfolioState（原地更新后返回同一对象）。"""
    et = str(event.event_type)
    acct = state.account
    cash = acct.cash

    if et == "BUY_FILLED":
        pos = _get_pos(state, event.instrument_key)
        q = float(event.quantity)
        px = float(event.price)
        fee = float(event.fee)
        notional = q * px
        new_qty = float(pos.quantity) + q
        if new_qty <= 0:
            avg = 0.0
        else:
            # 加权平均成本
            avg = (float(pos.avg_cost) * float(pos.quantity) + notional) / new_qty
        pos = pos.model_copy(
            update={
                "quantity": new_qty,
                "available_quantity": float(pos.available_quantity) + q,
                "avg_cost": avg,
                "as_of": event.trading_date or pos.as_of,
            }
        )
        spend = notional + fee
        if float(cash.available_cash) + 1e-9 < spend:
            raise ReducerError(
                f"insufficient cash for BUY {event.instrument_key}: "
                f"need {spend}, have {cash.available_cash}"
            )
        cash = CashBalance(
            currency=cash.currency,
            available_cash=float(cash.available_cash) - spend,
            frozen_cash=float(cash.frozen_cash),
        )
        pnl = acct.pnl.model_copy(
            update={"fees": float(acct.pnl.fees) + fee}
        )
        acct = acct.model_copy(update={"cash": cash, "pnl": pnl})
        _put_pos(state, pos)

    elif et == "SELL_FILLED":
        pos = _get_pos(state, event.instrument_key)
        q = float(event.quantity)
        px = float(event.price)
        fee = float(event.fee)
        if float(pos.available_quantity) + 1e-9 < q:
            raise ReducerError(
                f"insufficient available qty for SELL {event.instrument_key}: "
                f"need {q}, have {pos.available_quantity}"
            )
        realized = (px - float(pos.avg_cost)) * q
        new_qty = float(pos.quantity) - q
        new_avail = float(pos.available_quantity) - q
        proceeds = q * px - fee
        pos = pos.model_copy(
            update={
                "quantity": max(0.0, new_qty),
                "available_quantity": max(0.0, new_avail),
                "avg_cost": float(pos.avg_cost) if new_qty > 1e-12 else 0.0,
                "as_of": event.trading_date or pos.as_of,
            }
        )
        cash = CashBalance(
            currency=cash.currency,
            available_cash=float(cash.available_cash) + proceeds,
            frozen_cash=float(cash.frozen_cash),
        )
        pnl = acct.pnl.model_copy(
            update={
                "realized_pnl": float(acct.pnl.realized_pnl) + realized,
                "fees": float(acct.pnl.fees) + fee,
            }
        )
        acct = acct.model_copy(update={"cash": cash, "pnl": pnl})
        _put_pos(state, pos)

    elif et == "FREEZE":
        pos = _get_pos(state, event.instrument_key)
        q = float(event.quantity)
        if float(pos.available_quantity) + 1e-9 < q:
            raise ReducerError(f"cannot FREEZE {q} of {event.instrument_key}")
        pos = pos.model_copy(
            update={
                "available_quantity": float(pos.available_quantity) - q,
                "frozen_quantity": float(pos.frozen_quantity) + q,
            }
        )
        _put_pos(state, pos)

    elif et == "UNFREEZE":
        pos = _get_pos(state, event.instrument_key)
        q = float(event.quantity)
        if float(pos.frozen_quantity) + 1e-9 < q:
            raise ReducerError(f"cannot UNFREEZE {q} of {event.instrument_key}")
        pos = pos.model_copy(
            update={
                "available_quantity": float(pos.available_quantity) + q,
                "frozen_quantity": float(pos.frozen_quantity) - q,
            }
        )
        _put_pos(state, pos)

    elif et in ("TRANSFER_IN", "ADJUSTMENT") and event.instrument_key:
        pos = _get_pos(state, event.instrument_key)
        q = float(event.quantity)
        pos = pos.model_copy(
            update={
                "quantity": float(pos.quantity) + q,
                "available_quantity": float(pos.available_quantity) + q,
                "avg_cost": float(event.price) if event.price else pos.avg_cost,
                "as_of": event.trading_date or pos.as_of,
            }
        )
        _put_pos(state, pos)
        if event.cash_delta:
            cash = CashBalance(
                currency=cash.currency,
                available_cash=float(cash.available_cash) + float(event.cash_delta),
                frozen_cash=float(cash.frozen_cash),
            )
            acct = acct.model_copy(update={"cash": cash})

    elif et == "TRANSFER_OUT":
        pos = _get_pos(state, event.instrument_key)
        q = float(event.quantity)
        if float(pos.available_quantity) + 1e-9 < q:
            raise ReducerError(f"cannot TRANSFER_OUT {q}")
        pos = pos.model_copy(
            update={
                "quantity": float(pos.quantity) - q,
                "available_quantity": float(pos.available_quantity) - q,
            }
        )
        _put_pos(state, pos)

    elif et == "CORPORATE_ACTION":
        # payload 驱动：split_ratio / cash_dividend 等由 corporate_action 模块预先填好 quantity/cash_delta
        if event.instrument_key and event.quantity != 0:
            pos = _get_pos(state, event.instrument_key)
            # quantity 字段表示「调整后数量」增量或绝对？约定：payload.replace_qty 为绝对量
            if event.payload.get("replace_qty") is not None:
                new_q = float(event.payload["replace_qty"])
                ratio = float(event.payload.get("split_ratio") or 1.0)
                avg = float(pos.avg_cost) / ratio if ratio else pos.avg_cost
                pos = pos.model_copy(
                    update={
                        "quantity": new_q,
                        "available_quantity": new_q - float(pos.frozen_quantity),
                        "avg_cost": avg,
                    }
                )
            else:
                q = float(event.quantity)
                pos = pos.model_copy(
                    update={
                        "quantity": float(pos.quantity) + q,
                        "available_quantity": float(pos.available_quantity) + q,
                    }
                )
            _put_pos(state, pos)
        if event.cash_delta:
            cash = CashBalance(
                currency=cash.currency,
                available_cash=float(cash.available_cash) + float(event.cash_delta),
                frozen_cash=float(cash.frozen_cash),
            )
            acct = acct.model_copy(update={"cash": cash})

    elif et == "MARK_TO_MARKET":
        # 仅更新市值 / unrealized，由调用方在 MTM 后写 market_value
        pass

    else:
        # 未知类型：忽略数量变更，允许审计消息
        pass

    state.account = acct
    state.event_seq = int(state.event_seq) + 1
    return state


def apply_events(
    state: PortfolioState, events: Sequence[PositionEvent]
) -> PortfolioState:
    for ev in events:
        apply_event(state, ev)
    return state


def assert_invariants(state: PortfolioState) -> None:
    """校验 quantity / cash 不变量。"""
    cash = state.account.cash
    if float(cash.available_cash) < -1e-6 or float(cash.frozen_cash) < -1e-6:
        raise ReducerError("cash invariant violated")
    for pos in state.positions.values():
        q = float(pos.quantity)
        av = float(pos.available_quantity)
        fr = float(pos.frozen_quantity)
        if abs(q - (av + fr)) > 1e-6:
            raise ReducerError(
                f"qty invariant violated for {pos.instrument_key}: "
                f"{q} != {av}+{fr}"
            )
        if av < -1e-6 or fr < -1e-6:
            raise ReducerError(f"negative qty for {pos.instrument_key}")
