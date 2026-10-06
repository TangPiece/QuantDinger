"""ResearchExecutionSimulator：门面包装 3C ExecutionSimulator（非 Production）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from app.services.research_data.backtest.execution.models import MarketBar
from app.services.research_data.backtest.execution.simulator import (
    ExecutionSimulator,
    StepResult,
)
from app.services.research_data.backtest.ledger import PortfolioSnapshot
from app.services.research_data.backtest.policy import (
    BacktestMarketPricePolicy,
    CostPolicy,
    ExecutionPolicy,
    TradingRule,
)
from app.services.research_data.contracts import OrderIntent

from .order_builder import build_order_intents, portfolio_from_shares
from .price import assert_execution_price_raw
from .protocol import DailyCostRow, FillRow


class ResearchExecutionSimulator:
    """研究侧 OHLCV 执行仿真；内部复用 3C，不调用 ProductionBacktestEngine。"""

    def __init__(
        self,
        execution_policy: ExecutionPolicy,
        trading_rule: TradingRule,
        cost_policy: CostPolicy,
        market_price_policy: BacktestMarketPricePolicy | None = None,
        *,
        calendar: list[date] | None = None,
    ) -> None:
        assert_execution_price_raw()
        # 强制执行价 none
        mpp = market_price_policy or BacktestMarketPricePolicy(adjustment="none")
        if mpp.adjustment != "none":
            mpp = mpp.model_copy(update={"adjustment": "none"})
        self.cost_policy = cost_policy
        self.trading_rule = trading_rule
        self.execution_policy = execution_policy
        self._sim = ExecutionSimulator(
            execution_policy,
            trading_rule,
            cost_policy,
            mpp,
            calendar=calendar,
        )
        self.unsupported_algorithms: list[str] = []

    def step_weights(
        self,
        *,
        trading_date: date,
        target_weights: Mapping[str, float],
        cash: float,
        shares: Mapping[str, float],
        price_index: Mapping[tuple[str, date], Mapping[str, Any]],
        strategy_hash: str = "",
        trading_status: Mapping[tuple[str, date], Mapping[str, Any]] | None = None,
    ) -> tuple[float, dict[str, float], StepResult, DailyCostRow, list[FillRow]]:
        """按目标权重生成 OrderIntent 并执行一日。

        返回 ``(new_cash, new_shares, step, cost_row, fill_rows)``。
        """
        fill_field = self.execution_policy.execution_price or "open"
        prices: dict[str, float] = {}
        # 收集相关标的
        keys = set(target_weights) | set(shares)
        bars: dict[str, MarketBar] = {}
        status = trading_status or {}
        for ik in keys:
            bar_raw = price_index.get((ik, trading_date)) or {}
            st = status.get((ik, trading_date)) or {}
            o = bar_raw.get("open")
            c = bar_raw.get("close")
            px = bar_raw.get(fill_field)
            if px is not None and px == px and float(px) > 0:
                prices[ik] = float(px)
            elif c is not None and c == c and float(c) > 0:
                prices[ik] = float(c)
            bars[ik] = MarketBar(
                instrument_key=ik,
                trading_date=trading_date.isoformat(),
                open=float(o) if o is not None and o == o else None,
                high=float(bar_raw["high"])
                if bar_raw.get("high") is not None
                else None,
                low=float(bar_raw["low"]) if bar_raw.get("low") is not None else None,
                close=float(c) if c is not None and c == c else None,
                vwap=float(bar_raw["vwap"])
                if bar_raw.get("vwap") is not None
                else None,
                is_suspended=bool(st.get("is_suspended", False)),
                is_limit_up=bool(st.get("is_limit_up", False)),
                is_limit_down=bool(st.get("is_limit_down", False)),
                upper_limit=st.get("upper_limit"),
                lower_limit=st.get("lower_limit"),
            )

        portfolio = portfolio_from_shares(
            trading_date=trading_date,
            cash=cash,
            shares=shares,
            prices=prices,
        )
        intents, warnings = build_order_intents(
            target_weights,
            portfolio=portfolio,
            prices=prices,
            execution_date=trading_date,
            trading_rule=self.trading_rule,
            strategy_hash=strategy_hash,
        )
        for w in warnings:
            if w not in self.unsupported_algorithms:
                self.unsupported_algorithms.append(w)

        step = self._sim.step(
            trading_date=trading_date.isoformat(),
            intents=intents,
            bars=bars,
            portfolio=portfolio,
        )
        new_cash, new_shares = _portfolio_to_shares(step.portfolio)
        cost_row, fill_rows = _summarize_step(trading_date, step)
        return new_cash, new_shares, step, cost_row, fill_rows


def _portfolio_to_shares(
    portfolio: PortfolioSnapshot | None,
) -> tuple[float, dict[str, float]]:
    if portfolio is None:
        return 0.0, {}
    shares = {
        p.instrument_key: float(p.quantity or 0.0)
        for p in (portfolio.positions or [])
        if abs(float(p.quantity or 0.0)) > 1e-12
    }
    return float(portfolio.cash or 0.0), shares


def _summarize_step(trading_date: date, step: StepResult) -> tuple[DailyCostRow, list[FillRow]]:
    commission = stamp = transfer = slippage = 0.0
    for c in step.cost_breakdowns or []:
        commission += float(c.commission or 0.0)
        stamp += float(c.stamp_tax or 0.0)
        transfer += float(c.transfer_fee or 0.0)
        slippage += float(c.slippage or 0.0)
    fills: list[FillRow] = []
    n_fills = 0
    n_rejects = 0
    for t in step.trades or []:
        if t.status in ("FILLED", "PARTIAL"):
            n_fills += 1
        elif t.status == "REJECTED":
            n_rejects += 1
        fills.append(
            FillRow(
                trading_date=trading_date,
                trade_id=t.trade_id,
                instrument_key=t.instrument_key,
                side=t.side,
                quantity=float(t.quantity or 0.0),
                executed_price=t.executed_price,
                commission=float(t.commission or 0.0),
                tax=float(t.tax or 0.0),
                slippage=float(t.slippage or 0.0),
                status=t.status,
                reject_reason=t.reject_reason,
            )
        )
    total = commission + stamp + transfer + slippage
    return (
        DailyCostRow(
            trading_date=trading_date,
            commission=commission,
            stamp_tax=stamp,
            transfer_fee=transfer,
            slippage=slippage,
            total_cost=total,
            n_fills=n_fills,
            n_rejects=n_rejects,
        ),
        fills,
    )
