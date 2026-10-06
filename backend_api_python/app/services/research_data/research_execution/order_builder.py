"""目标权重 → OrderIntent（研究侧标准接口）。"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Mapping

from app.services.research_data.backtest.ledger import PortfolioSnapshot, PositionSnapshot
from app.services.research_data.backtest.policy import TradingRule
from app.services.research_data.backtest.execution.rebalance import (
    target_quantity_from_weight,
)
from app.services.research_data.contracts import OrderIntent, TargetPosition

from .algorithms import resolve_algorithm


def portfolio_from_shares(
    *,
    trading_date: date,
    cash: float,
    shares: Mapping[str, float],
    prices: Mapping[str, float],
) -> PortfolioSnapshot:
    """从研究账本构造 3C PortfolioSnapshot。"""
    positions: list[PositionSnapshot] = []
    mv = 0.0
    day = trading_date.isoformat()
    for ik, qty in shares.items():
        if abs(float(qty)) < 1e-12:
            continue
        px = float(prices.get(ik) or 0.0)
        valued = float(qty) * px
        mv += valued
        positions.append(
            PositionSnapshot(
                instrument_key=ik,
                trading_date=day,
                quantity=float(qty),
                average_cost=px if px else None,
                market_value=valued,
            )
        )
    total = float(cash) + mv
    return PortfolioSnapshot(
        trading_date=day,
        cash=float(cash),
        total_value=total,
        positions=positions,
    )


def weights_to_target_positions(
    weights: Mapping[str, float],
    *,
    trading_date: date,
    strategy_hash: str = "",
) -> list[TargetPosition]:
    """执行日目标权重 → TargetPosition 列表。"""
    ts = datetime.combine(trading_date, time(15, 0, 0))
    out: list[TargetPosition] = []
    for ik, w in weights.items():
        out.append(
            TargetPosition(
                instrument_key=str(ik),
                trading_date=trading_date.isoformat(),
                portfolio_id=(strategy_hash or "research")[:16],
                strategy_version="qd_research_execution@1",
                dataset_hash=strategy_hash or "",
                timestamp=ts,
                target_weight=float(w),
            )
        )
    return out


def build_order_intents(
    weights: Mapping[str, float],
    *,
    portfolio: PortfolioSnapshot,
    prices: Mapping[str, float],
    execution_date: date,
    trading_rule: TradingRule,
    strategy_hash: str = "",
    execution_algorithm: str = "MARKET",
) -> tuple[list[OrderIntent], list[str]]:
    """权重 vs 当前持仓 → OrderIntent；返回 (intents, warnings)。

    ``intended_execution_time`` 钉在执行日（研究层已完成 delay 映射）。
    """
    warnings: list[str] = []
    algo = resolve_algorithm(execution_algorithm)
    if not algo.is_supported():
        warnings.append(f"unsupported_algorithm:{algo.name};fallback=MARKET")
        execution_algorithm = "MARKET"

    targets = weights_to_target_positions(
        weights, trading_date=execution_date, strategy_hash=strategy_hash
    )
    pos_map = {
        p.instrument_key: float(p.quantity or 0.0) for p in (portfolio.positions or [])
    }
    portfolio_value = float(portfolio.total_value or 0.0)
    if portfolio_value <= 0:
        mv = 0.0
        for ik, qty in pos_map.items():
            px = float(prices.get(ik) or 0.0)
            mv += qty * px
        portfolio_value = float(portfolio.cash or 0.0) + mv

    intended = datetime.combine(execution_date, time(9, 30, 0))
    intents: list[OrderIntent] = []
    seen: set[str] = set()

    for t in targets:
        ik = t.instrument_key
        seen.add(ik)
        current = float(pos_map.get(ik, 0.0))
        px = float(prices.get(ik) or 0.0)
        w = float(t.target_weight or 0.0)
        target_qty = target_quantity_from_weight(
            target_weight=w, portfolio_value=portfolio_value, price=px
        )
        # 空头：TradingRule.short_allowed=False 时仍生成意图，由 simulator 拒绝
        delta = target_qty - current
        if abs(delta) < 1e-9:
            continue
        side = "BUY" if delta > 0 else "SELL"
        intents.append(
            OrderIntent(
                instrument_key=ik,
                side=side,
                quantity=abs(delta),
                execution_algorithm=execution_algorithm,  # type: ignore[arg-type]
                trading_date=execution_date.isoformat(),
                target_quantity=target_qty,
                current_quantity=current,
                quantity_delta=delta,
                intended_execution_time=intended,
                strategy_version=t.strategy_version,
                reason="REBALANCE",
            )
        )

    # 未在目标中的旧仓 → 清仓
    for ik, current in pos_map.items():
        if ik in seen or abs(current) < 1e-9:
            continue
        side = "SELL" if current > 0 else "BUY"
        intents.append(
            OrderIntent(
                instrument_key=ik,
                side=side,  # type: ignore[arg-type]
                quantity=abs(current),
                execution_algorithm="MARKET",
                trading_date=execution_date.isoformat(),
                target_quantity=0.0,
                current_quantity=current,
                quantity_delta=-current,
                intended_execution_time=intended,
                reason="FLATTEN",
            )
        )

    _ = trading_rule  # lot 在 simulator 内处理
    return intents, warnings
