"""ResearchBacktestEngine：权重 → 简化份额账本 → 日 NAV（无成本）。"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from .benchmark import (
    attach_benchmark,
    benchmark_metrics_from_returns,
    excess_metrics,
    resolve_benchmark_returns,
)
from .calendar import trading_calendar_from_bars
from .cost import ExecutionCostModel, NoCostModel
from .execution import map_targets_to_execution
from .hash import compute_backtest_hash
from .metrics import compute_performance
from .protocol import (
    BacktestFrames,
    BacktestPositionRow,
    BacktestSpec,
    DailyReturnRow,
    NavPoint,
    TurnoverRow,
)


def _finite(v: float) -> bool:
    return v == v and v not in (float("inf"), float("-inf"))


class ResearchBacktestEngine:
    """日循环：rebalance(at fill) → mark(close) → return。"""

    def __init__(self, *, cost_model: ExecutionCostModel | None = None) -> None:
        self._cost = cost_model or NoCostModel()

    def run(
        self,
        spec: BacktestSpec,
        *,
        targets_by_signal_date: Mapping[date, list[dict[str, Any]]],
        price_index: Mapping[tuple[str, date], Mapping[str, float]],
        metadata: Mapping[str, Any] | None = None,
    ) -> BacktestFrames:
        """执行研究回测；不调用 Production ExecutionSimulator。"""
        meta = dict(metadata or {})
        bhash = compute_backtest_hash(spec)
        calendar = trading_calendar_from_bars(
            price_index, start=spec.start_date, end=spec.end_date
        )
        if not calendar:
            return BacktestFrames(
                backtest_hash=bhash,
                strategy_hash=spec.strategy_hash,
                metadata={"warning": "empty_calendar"},
            )

        exec_targets = map_targets_to_execution(
            targets_by_signal_date, calendar, spec.execution_policy
        )
        fill_field = spec.execution_policy.fill_field

        cash = float(spec.initial_nav)
        shares: dict[str, float] = {}
        last_close: dict[str, float] = {}

        nav_rows: list[NavPoint] = []
        ret_rows: list[DailyReturnRow] = []
        pos_rows: list[BacktestPositionRow] = []
        turn_rows: list[TurnoverRow] = []
        prev_nav: float | None = None
        first_rebalance = True

        for d in calendar:
            # --- rebalance at fill ---
            rebalanced = False
            turnover_val: float | None = None
            if d in exec_targets:
                targets = exec_targets[d]
                # 调仓前市值权重
                pre_nav = self._mark_nav(cash, shares, d, price_index, last_close)
                w_old = self._mv_weights(shares, d, price_index, last_close, pre_nav)
                w_new = dict(targets)
                # 换手：首调仓记 full deploy；其后 0.5 * L1
                if first_rebalance:
                    turnover_val = None
                    first_rebalance = False
                else:
                    keys = set(w_old) | set(w_new)
                    turnover_val = 0.5 * sum(
                        abs(w_new.get(k, 0.0) - w_old.get(k, 0.0)) for k in keys
                    )
                cash, shares = self._rebalance(
                    pre_nav,
                    targets,
                    d,
                    price_index,
                    fill_field,
                )
                rebalanced = True
                # NoCost：预留扣费钩子（始终 0）
                _ = self._cost.cost_for_trade(notional=pre_nav, side="REBALANCE")

            turn_rows.append(
                TurnoverRow(
                    trading_date=d, turnover=turnover_val, rebalanced=rebalanced
                )
            )

            # --- mark at close ---
            nav, cash_mtm, gross, day_pos = self._close_mark(
                cash, shares, d, price_index, last_close
            )
            cash = cash_mtm
            nav_rows.append(
                NavPoint(
                    trading_date=d, nav=nav, cash=cash, gross_exposure=gross
                )
            )
            pos_rows.extend(day_pos)

            pr: float | None = None
            if prev_nav is not None and prev_nav > 0:
                pr = nav / prev_nav - 1.0
            ret_rows.append(
                DailyReturnRow(trading_date=d, portfolio_return=pr)
            )
            prev_nav = nav

        bench = resolve_benchmark_returns(
            calendar,
            mode=spec.benchmark_mode,
            instrument_key=spec.benchmark_instrument_key,
            price_index=price_index,
            metadata=meta,
        )
        ret_rows = attach_benchmark(ret_rows, bench)
        metrics = compute_performance(
            nav_rows, ret_rows, turn_rows, initial_nav=spec.initial_nav
        )
        bench_metrics: dict[str, Any] = {}
        if spec.benchmark_mode != "NONE":
            bench_metrics = {
                "benchmark": benchmark_metrics_from_returns(
                    ret_rows, initial_nav=spec.initial_nav
                ),
                "excess": excess_metrics(ret_rows),
            }

        return BacktestFrames(
            backtest_hash=bhash,
            strategy_hash=spec.strategy_hash,
            nav=nav_rows,
            returns=ret_rows,
            positions=pos_rows,
            turnover=turn_rows,
            metrics=metrics.model_dump(mode="json"),
            benchmark_metrics=bench_metrics,
            metadata={
                "allows_same_close": spec.execution_policy.allows_same_close,
                "execution_policy": spec.execution_policy.mode,
                "fill_field": fill_field,
                "n_calendar_days": len(calendar),
                "n_rebalance_days": len(exec_targets),
            },
        )

    def _price(
        self,
        inst: str,
        d: date,
        price_index: Mapping[tuple[str, date], Mapping[str, float]],
        field: str,
        last_close: Mapping[str, float],
    ) -> float | None:
        bar = price_index.get((inst, d))
        if bar:
            v = float(bar.get(field, float("nan")))
            if _finite(v) and v > 0:
                return v
            # close 缺失时尝试昨收
            if field == "close":
                lc = last_close.get(inst)
                if lc is not None and _finite(lc) and lc > 0:
                    return float(lc)
        elif field == "close":
            lc = last_close.get(inst)
            if lc is not None and _finite(lc) and lc > 0:
                return float(lc)
        return None

    def _mark_nav(
        self,
        cash: float,
        shares: Mapping[str, float],
        d: date,
        price_index: Mapping[tuple[str, date], Mapping[str, float]],
        last_close: Mapping[str, float],
    ) -> float:
        total = float(cash)
        for inst, qty in shares.items():
            px = self._price(inst, d, price_index, "close", last_close)
            if px is None:
                # 缺价：用 fill/open 兜底估市值，再不行记 0
                px = self._price(inst, d, price_index, "open", last_close) or 0.0
            total += float(qty) * float(px)
        return total

    def _mv_weights(
        self,
        shares: Mapping[str, float],
        d: date,
        price_index: Mapping[tuple[str, date], Mapping[str, float]],
        last_close: Mapping[str, float],
        nav: float,
    ) -> dict[str, float]:
        if nav <= 0:
            return {}
        out: dict[str, float] = {}
        for inst, qty in shares.items():
            px = self._price(inst, d, price_index, "close", last_close)
            if px is None:
                px = self._price(inst, d, price_index, "open", last_close)
            if px is None:
                continue
            out[inst] = float(qty) * float(px) / nav
        return out

    def _rebalance(
        self,
        nav: float,
        targets: Mapping[str, float],
        d: date,
        price_index: Mapping[tuple[str, date], Mapping[str, float]],
        fill_field: str,
    ) -> tuple[float, dict[str, float]]:
        """按目标权重用 fill 价换 shares；缺价 SKIP_TO_CASH。"""
        new_shares: dict[str, float] = {}
        invested = 0.0
        for inst, w in targets.items():
            bar = price_index.get((inst, d))
            if not bar:
                continue
            px = float(bar.get(fill_field, float("nan")))
            if not _finite(px) or px <= 0:
                continue
            qty = nav * float(w) / px
            new_shares[inst] = qty
            invested += qty * px
        cash = nav - invested
        return cash, new_shares

    def _close_mark(
        self,
        cash: float,
        shares: Mapping[str, float],
        d: date,
        price_index: Mapping[tuple[str, date], Mapping[str, float]],
        last_close: dict[str, float],
    ) -> tuple[float, float, float, list[BacktestPositionRow]]:
        """收盘盯市；更新 last_close。"""
        mv = 0.0
        gross = 0.0
        rows: list[BacktestPositionRow] = []
        priced: dict[str, float] = {}
        for inst, qty in shares.items():
            px = self._price(inst, d, price_index, "close", last_close)
            if px is None:
                # 诊断：市值计 0，不硬失败
                px = 0.0
            else:
                last_close[inst] = px
            valued = float(qty) * float(px)
            mv += valued
            gross += abs(valued)
            priced[inst] = px

        nav = float(cash) + mv
        for inst, qty in shares.items():
            px = priced.get(inst, 0.0)
            w = (float(qty) * px / nav) if nav else 0.0
            rows.append(
                BacktestPositionRow(
                    trading_date=d,
                    instrument_key=inst,
                    shares=float(qty),
                    weight=w,
                    price=float(px),
                )
            )
        return nav, float(cash), gross, rows
