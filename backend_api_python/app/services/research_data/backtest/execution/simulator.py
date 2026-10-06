"""日频 ExecutionSimulator：规则 + 成本 → Trade / Position（非 Production 全引擎）。"""

from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Mapping, Sequence

from app.services.research_data.backtest.ledger import (
    PortfolioSnapshot,
    PositionSnapshot,
    TradeRecord,
)
from app.services.research_data.backtest.policy import (
    BacktestMarketPricePolicy,
    CostPolicy,
    ExecutionPolicy,
    TradingRule,
)
from app.services.research_data.contracts import OrderIntent, TargetPosition

from .calendar import resolve_execution_date
from .cost import compute_cost_breakdown
from .eligibility import decide_execution
from .lot import round_price_to_tick
from .models import (
    REASON_EXECUTION_DELAY,
    REASON_INSUFFICIENT_CASH,
    CostBreakdown,
    ExecutionDecision,
    MarketBar,
)
from .rebalance import targets_to_order_intents


def _parse_day(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip()[:10])


def resolve_fill_price(
    bar: MarketBar,
    execution_policy: ExecutionPolicy,
    market_price_policy: BacktestMarketPricePolicy,
) -> float | None:
    """按政策取成交价字段。"""
    key = execution_policy.execution_price or market_price_policy.reference_price or "close"
    mapping = {
        "open": bar.open,
        "close": bar.close,
        "vwap": bar.vwap if bar.vwap is not None else bar.close,
        "mid": None,
        "limit_ref": bar.close,
        "adj_close": bar.close,
    }
    if key == "mid":
        if bar.high is not None and bar.low is not None:
            return (float(bar.high) + float(bar.low)) / 2.0
        return bar.close
    return mapping.get(key, bar.close)


@dataclass
class StepResult:
    """单日模拟结果。"""

    trading_date: str
    decisions: list[ExecutionDecision] = field(default_factory=list)
    trades: list[TradeRecord] = field(default_factory=list)
    cost_breakdowns: list[CostBreakdown] = field(default_factory=list)
    portfolio: PortfolioSnapshot | None = None


@dataclass
class PipelineResult:
    """Target → Intent → Decision → Trade → Position 完整链路结果。"""

    intents: list[OrderIntent]
    decisions: list[ExecutionDecision]
    trades: list[TradeRecord]
    portfolio: PortfolioSnapshot
    cost_breakdowns: list[CostBreakdown] = field(default_factory=list)


class ExecutionSimulator:
    """引擎无关日频执行模拟器。"""

    def __init__(
        self,
        execution_policy: ExecutionPolicy,
        trading_rule: TradingRule,
        cost_policy: CostPolicy,
        market_price_policy: BacktestMarketPricePolicy | None = None,
        *,
        calendar=None,
    ) -> None:
        self.execution_policy = execution_policy
        self.trading_rule = trading_rule
        self.cost_policy = cost_policy
        self.market_price_policy = market_price_policy or BacktestMarketPricePolicy()
        self.calendar = calendar
        # instrument_key → 当日买入数量（用于 T+1 可卖）
        self._bought_today: dict[str, float] = {}
        self._last_date: str | None = None

    def _roll_day(self, trading_date: str) -> None:
        if self._last_date != trading_date:
            self._bought_today = {}
            self._last_date = trading_date

    def sellable_quantity(self, instrument_key: str, position_qty: float) -> float:
        """t_plus>=1 时扣除当日买入。"""
        pos = max(0.0, float(position_qty))
        if int(self.trading_rule.t_plus or 0) <= 0:
            return pos
        bought = float(self._bought_today.get(instrument_key, 0.0))
        return max(0.0, pos - bought)

    def step(
        self,
        *,
        trading_date: str,
        intents: Sequence[OrderIntent],
        bars: Mapping[str, MarketBar],
        portfolio: PortfolioSnapshot,
    ) -> StepResult:
        """处理计划在 ``trading_date`` 执行的 intents。"""
        self._roll_day(trading_date)
        day = _parse_day(trading_date)
        cash = float(portfolio.cash or 0.0)
        pos_map: dict[str, PositionSnapshot] = {
            p.instrument_key: deepcopy(p) for p in (portfolio.positions or [])
        }

        decisions: list[ExecutionDecision] = []
        trades: list[TradeRecord] = []
        costs: list[CostBreakdown] = []

        for intent in intents:
            # 执行日门控：intended 日不等于今日 → EXECUTION_DELAY
            intended = intent.intended_execution_time
            if intended is not None:
                if _parse_day(intended) != day:
                    decisions.append(
                        ExecutionDecision(
                            instrument_key=intent.instrument_key,
                            side=intent.side,
                            executable=False,
                            reason=REASON_EXECUTION_DELAY,
                            requested_quantity=abs(float(intent.quantity)),
                            executable_quantity=0.0,
                            rejected_quantity=abs(float(intent.quantity)),
                        )
                    )
                    continue
            elif intent.trading_date:
                # 无 intended 时用 delay 从 signal trading_date 推算
                try:
                    exec_day = resolve_execution_date(
                        intent.trading_date,
                        self.execution_policy.execution_delay,
                        market_calendar_id=self.trading_rule.market_calendar_id,
                        calendar=self.calendar,
                    )
                except Exception:
                    exec_day = day
                if exec_day != day:
                    decisions.append(
                        ExecutionDecision(
                            instrument_key=intent.instrument_key,
                            side=intent.side,
                            executable=False,
                            reason=REASON_EXECUTION_DELAY,
                            requested_quantity=abs(float(intent.quantity)),
                            executable_quantity=0.0,
                            rejected_quantity=abs(float(intent.quantity)),
                        )
                    )
                    continue

            bar = bars.get(intent.instrument_key)
            fill = resolve_fill_price(bar, self.execution_policy, self.market_price_policy) if bar else None
            if fill is not None:
                fill = round_price_to_tick(fill, self.trading_rule.tick_size)

            cur_qty = float(pos_map[intent.instrument_key].quantity) if intent.instrument_key in pos_map else 0.0
            sellable = (
                self.sellable_quantity(intent.instrument_key, cur_qty)
                if intent.side == "SELL"
                else None
            )

            decision = decide_execution(
                instrument_key=intent.instrument_key,
                side=intent.side,
                quantity=float(intent.quantity),
                bar=bar,
                rule=self.trading_rule,
                sellable_quantity=sellable,
                fill_price=fill,
            )

            if not decision.executable or decision.executable_quantity <= 0:
                decisions.append(decision)
                # 记录拒单 TradeRecord 便于审计
                trades.append(
                    TradeRecord(
                        trade_id=f"rej_{uuid.uuid4().hex[:12]}",
                        instrument_key=intent.instrument_key,
                        side=intent.side,
                        quantity=0.0,
                        requested_price=fill,
                        executed_price=None,
                        signal_time=intent.signal_time,
                        order_time=intent.intended_execution_time,
                        execution_time=None,
                        status="REJECTED",
                        signal_id=intent.signal_id,
                        reject_reason=decision.reason,
                    )
                )
                continue

            qty = float(decision.executable_quantity)
            price = float(decision.fill_price or 0.0)
            breakdown = compute_cost_breakdown(
                side=intent.side,
                quantity=qty,
                executed_price=price,
                cost_policy=self.cost_policy,
            )

            # 现金约束（买入）
            if intent.side == "BUY" and self.trading_rule.enforce_cash:
                need = abs(breakdown.net_cash_delta)
                if need > cash + 1e-9:
                    # 按现金能买的最大整手
                    affordable_gross = max(0.0, cash)
                    if price <= 0:
                        decision = decision.model_copy(
                            update={
                                "executable": False,
                                "executable_quantity": 0.0,
                                "rejected_quantity": decision.requested_quantity,
                                "reason": REASON_INSUFFICIENT_CASH,
                            }
                        )
                        decisions.append(decision)
                        continue
                    max_qty = affordable_gross / price
                    from .lot import adjust_lot_quantity

                    lot_adj = adjust_lot_quantity(max_qty, self.trading_rule)
                    if lot_adj.executable_quantity <= 0:
                        decision = decision.model_copy(
                            update={
                                "executable": False,
                                "executable_quantity": 0.0,
                                "rejected_quantity": decision.requested_quantity,
                                "reason": REASON_INSUFFICIENT_CASH,
                            }
                        )
                        decisions.append(decision)
                        continue
                    qty = lot_adj.executable_quantity
                    decision = decision.model_copy(
                        update={
                            "executable_quantity": qty,
                            "rejected_quantity": decision.requested_quantity - qty,
                            "reason": REASON_INSUFFICIENT_CASH
                            if qty < decision.requested_quantity
                            else decision.reason,
                        }
                    )
                    breakdown = compute_cost_breakdown(
                        side="BUY",
                        quantity=qty,
                        executed_price=price,
                        cost_policy=self.cost_policy,
                    )

            decisions.append(decision)
            costs.append(breakdown)

            # 更新现金与持仓
            cash += breakdown.net_cash_delta
            if intent.side == "BUY":
                prev = pos_map.get(intent.instrument_key)
                prev_qty = float(prev.quantity) if prev else 0.0
                prev_cost = float(prev.average_cost or price) if prev else price
                new_qty = prev_qty + qty
                avg = (
                    (prev_qty * prev_cost + qty * price) / new_qty
                    if new_qty > 0
                    else price
                )
                pos_map[intent.instrument_key] = PositionSnapshot(
                    instrument_key=intent.instrument_key,
                    trading_date=trading_date,
                    quantity=new_qty,
                    average_cost=avg,
                    market_value=new_qty * price,
                )
                self._bought_today[intent.instrument_key] = (
                    self._bought_today.get(intent.instrument_key, 0.0) + qty
                )
            else:
                prev = pos_map.get(intent.instrument_key)
                prev_qty = float(prev.quantity) if prev else 0.0
                new_qty = prev_qty - qty
                if new_qty <= 1e-12:
                    pos_map.pop(intent.instrument_key, None)
                else:
                    pos_map[intent.instrument_key] = PositionSnapshot(
                        instrument_key=intent.instrument_key,
                        trading_date=trading_date,
                        quantity=new_qty,
                        average_cost=prev.average_cost if prev else price,
                        market_value=new_qty * price,
                    )

            status = "FILLED"
            if decision.rejected_quantity > 1e-12:
                status = "PARTIAL"

            trades.append(
                TradeRecord(
                    trade_id=f"tr_{uuid.uuid4().hex[:12]}",
                    instrument_key=intent.instrument_key,
                    side=intent.side,
                    quantity=qty,
                    requested_price=fill,
                    executed_price=price,
                    signal_time=intent.signal_time,
                    order_time=intent.intended_execution_time,
                    execution_time=datetime(
                        day.year, day.month, day.day,
                        9 if self.execution_policy.execution_price == "open" else 15,
                        30 if self.execution_policy.execution_price == "open" else 0,
                    ),
                    commission=breakdown.commission + breakdown.transfer_fee,
                    tax=breakdown.stamp_tax,
                    slippage=breakdown.slippage,
                    status=status,
                    signal_id=intent.signal_id,
                    reject_reason=decision.reason if status == "PARTIAL" else None,
                )
            )

        # 市值重估
        positions = []
        total_mv = 0.0
        for ik, snap in pos_map.items():
            bar = bars.get(ik)
            px = resolve_fill_price(bar, self.execution_policy, self.market_price_policy) if bar else snap.average_cost
            px = float(px or 0.0)
            mv = float(snap.quantity) * px
            total_mv += mv
            positions.append(
                snap.model_copy(
                    update={
                        "trading_date": trading_date,
                        "market_value": mv,
                        "weight": None,
                    }
                )
            )
        total_value = cash + total_mv
        for i, p in enumerate(positions):
            if total_value > 0 and p.market_value is not None:
                positions[i] = p.model_copy(
                    update={"weight": float(p.market_value) / total_value}
                )

        new_port = PortfolioSnapshot(
            trading_date=trading_date,
            cash=cash,
            total_value=total_value,
            positions=positions,
        )
        return StepResult(
            trading_date=trading_date,
            decisions=decisions,
            trades=trades,
            cost_breakdowns=costs,
            portfolio=new_port,
        )


def run_pipeline(
    *,
    targets: Sequence[TargetPosition],
    portfolio: PortfolioSnapshot,
    bars: Mapping[str, MarketBar],
    execution_policy: ExecutionPolicy,
    trading_rule: TradingRule,
    cost_policy: CostPolicy,
    market_price_policy: BacktestMarketPricePolicy | None = None,
    execution_date: str | None = None,
    calendar=None,
) -> PipelineResult:
    """完整链路：Target → OrderIntent → Decision → Trade → Position。

    ``execution_date`` 默认取第一个 intent 的 intended 日或 target 的 T+delay。
    """
    prices = {}
    for ik, bar in bars.items():
        px = bar.open if execution_policy.execution_price == "open" else bar.close
        if px is not None:
            prices[ik] = float(px)

    intents = targets_to_order_intents(
        targets,
        portfolio=portfolio,
        prices=prices,
        execution_policy=execution_policy,
        trading_rule=trading_rule,
        calendar=calendar,
    )

    if execution_date is None:
        if intents and intents[0].intended_execution_time is not None:
            execution_date = intents[0].intended_execution_time.date().isoformat()
        elif targets:
            execution_date = resolve_execution_date(
                targets[0].trading_date,
                execution_policy.execution_delay,
                market_calendar_id=trading_rule.market_calendar_id,
                calendar=calendar,
            ).isoformat()
        else:
            execution_date = portfolio.trading_date

    sim = ExecutionSimulator(
        execution_policy,
        trading_rule,
        cost_policy,
        market_price_policy,
        calendar=calendar,
    )
    # 仅执行落在 execution_date 的 intents；其余记 DELAY
    result = sim.step(
        trading_date=execution_date,
        intents=intents,
        bars=bars,
        portfolio=portfolio,
    )
    assert result.portfolio is not None
    return PipelineResult(
        intents=list(intents),
        decisions=result.decisions,
        trades=result.trades,
        portfolio=result.portfolio,
        cost_breakdowns=result.cost_breakdowns,
    )
