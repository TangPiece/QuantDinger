"""TargetPosition + 当前持仓 → OrderIntent（正式再平衡路径）。"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from app.services.research_data.backtest.ledger import PortfolioSnapshot, PositionSnapshot
from app.services.research_data.backtest.policy import ExecutionPolicy, TradingRule
from app.services.research_data.contracts import OrderIntent, TargetPosition

from .calendar import intended_execution_datetime


def _position_qty_map(portfolio: PortfolioSnapshot | None) -> dict[str, float]:
    if portfolio is None:
        return {}
    out: dict[str, float] = {}
    for p in portfolio.positions or []:
        out[p.instrument_key] = out.get(p.instrument_key, 0.0) + float(p.quantity or 0.0)
    return out


def target_quantity_from_weight(
    *,
    target_weight: float,
    portfolio_value: float,
    price: float,
) -> float:
    """权重 → 目标股数（未做整手）。"""
    if price <= 0 or portfolio_value <= 0:
        return 0.0
    return float(target_weight) * float(portfolio_value) / float(price)


def targets_to_order_intents(
    targets: Sequence[TargetPosition],
    *,
    portfolio: PortfolioSnapshot | None,
    prices: Mapping[str, float],
    execution_policy: ExecutionPolicy,
    trading_rule: TradingRule,
    portfolio_value: float | None = None,
    calendar=None,
) -> list[OrderIntent]:
    """将目标仓位转为买卖 OrderIntent（含 delta 审计字段）。

    - 优先使用 ``target_quantity``；否则用 weight * portfolio_value / price
    - 未出现在 targets 但持仓>0 的标的 → 清仓 SELL
    - ``intended_execution_time`` 由 ExecutionPolicy.execution_delay 解析
    """
    pos_map = _position_qty_map(portfolio)
    if portfolio_value is None:
        portfolio_value = float(portfolio.total_value) if portfolio else 0.0
        if portfolio_value <= 0 and portfolio is not None:
            # 回退：现金 + 持仓市值估算
            mv = 0.0
            for p in portfolio.positions or []:
                px = prices.get(p.instrument_key)
                if px and p.quantity:
                    mv += float(p.quantity) * float(px)
            portfolio_value = float(portfolio.cash or 0.0) + mv

    intents: list[OrderIntent] = []
    seen: set[str] = set()

    for t in targets:
        ik = t.instrument_key
        seen.add(ik)
        current = float(pos_map.get(ik, 0.0))
        if t.target_quantity is not None:
            target_qty = float(t.target_quantity)
        else:
            px = float(prices.get(ik) or 0.0)
            w = float(t.target_weight or 0.0)
            target_qty = target_quantity_from_weight(
                target_weight=w, portfolio_value=portfolio_value, price=px
            )

        delta = target_qty - current
        if abs(delta) < 1e-9:
            continue

        side = "BUY" if delta > 0 else "SELL"
        qty = abs(delta)
        signal_time = t.timestamp if isinstance(t.timestamp, datetime) else None
        intended = intended_execution_datetime(
            t.trading_date,
            execution_policy.execution_delay,
            market_calendar_id=trading_rule.market_calendar_id,
            execution_price=execution_policy.execution_price,
            calendar=calendar,
        )
        intents.append(
            OrderIntent(
                instrument_key=ik,
                side=side,
                quantity=qty,
                signal_id=t.signal_id,
                strategy_version=t.strategy_version,
                trading_date=t.trading_date,
                target_quantity=target_qty,
                current_quantity=current,
                quantity_delta=delta,
                signal_time=signal_time,
                intended_execution_time=intended,
                reason="REBALANCE",
            )
        )

    # 清仓：targets 未覆盖的旧持仓
    for ik, current in pos_map.items():
        if ik in seen or abs(current) < 1e-9:
            continue
        # 用任一 target 的 trading_date，否则用 portfolio.trading_date
        trading_date = (
            targets[0].trading_date if targets else (portfolio.trading_date if portfolio else "")
        )
        intended = intended_execution_datetime(
            trading_date,
            execution_policy.execution_delay,
            market_calendar_id=trading_rule.market_calendar_id,
            execution_price=execution_policy.execution_price,
            calendar=calendar,
        )
        intents.append(
            OrderIntent(
                instrument_key=ik,
                side="SELL",
                quantity=abs(current),
                trading_date=trading_date,
                target_quantity=0.0,
                current_quantity=current,
                quantity_delta=-current,
                intended_execution_time=intended,
                reason="LIQUIDATE",
            )
        )

    return intents
