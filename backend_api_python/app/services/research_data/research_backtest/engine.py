"""ResearchBacktestEngine：GROSS 权重账本 / NET 执行仿真 → 日 NAV。"""

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
    """日循环：rebalance → mark → return；NET 走 5C 执行层。"""

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
        """执行研究回测；NET 复用 3C ExecutionSimulator，不调用 Production。"""
        if spec.realism == "NET":
            return self._run_net(
                spec,
                targets_by_signal_date=targets_by_signal_date,
                price_index=price_index,
                metadata=metadata,
            )
        return self._run_gross(
            spec,
            targets_by_signal_date=targets_by_signal_date,
            price_index=price_index,
            metadata=metadata,
        )

    def _run_gross(
        self,
        spec: BacktestSpec,
        *,
        targets_by_signal_date: Mapping[date, list[dict[str, Any]]],
        price_index: Mapping[tuple[str, date], Mapping[str, float]],
        metadata: Mapping[str, Any] | None = None,
    ) -> BacktestFrames:
        """5B 理想路径：权重瞬时换仓、无成本。"""
        meta = dict(metadata or {})
        meta["_price_index"] = price_index
        bhash = compute_backtest_hash(spec)
        calendar = trading_calendar_from_bars(
            price_index, start=spec.start_date, end=spec.end_date
        )
        if not calendar:
            return BacktestFrames(
                backtest_hash=bhash,
                strategy_hash=spec.strategy_hash,
                metadata={"warning": "empty_calendar", "realism": "GROSS"},
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
            rebalanced = False
            turnover_val: float | None = None
            if d in exec_targets:
                targets = exec_targets[d]
                pre_nav = self._mark_nav(cash, shares, d, price_index, last_close)
                w_old = self._mv_weights(shares, d, price_index, last_close, pre_nav)
                w_new = dict(targets)
                if first_rebalance:
                    turnover_val = None
                    first_rebalance = False
                else:
                    keys = set(w_old) | set(w_new)
                    turnover_val = 0.5 * sum(
                        abs(w_new.get(k, 0.0) - w_old.get(k, 0.0)) for k in keys
                    )
                cash, shares = self._rebalance(
                    pre_nav, targets, d, price_index, fill_field
                )
                rebalanced = True
                _ = self._cost.cost_for_trade(notional=pre_nav, side="REBALANCE")

            turn_rows.append(
                TurnoverRow(
                    trading_date=d, turnover=turnover_val, rebalanced=rebalanced
                )
            )
            nav, cash_mtm, gross, day_pos = self._close_mark(
                cash, shares, d, price_index, last_close
            )
            cash = cash_mtm
            nav_rows.append(
                NavPoint(trading_date=d, nav=nav, cash=cash, gross_exposure=gross)
            )
            pos_rows.extend(day_pos)
            pr: float | None = None
            if prev_nav is not None and prev_nav > 0:
                pr = nav / prev_nav - 1.0
            ret_rows.append(DailyReturnRow(trading_date=d, portfolio_return=pr))
            prev_nav = nav

        return self._finalize_frames(
            spec,
            bhash=bhash,
            calendar=calendar,
            exec_targets=exec_targets,
            nav_rows=nav_rows,
            ret_rows=ret_rows,
            pos_rows=pos_rows,
            turn_rows=turn_rows,
            meta=meta,
            fill_field=fill_field,
            realism="GROSS",
        )

    def _run_net(
        self,
        spec: BacktestSpec,
        *,
        targets_by_signal_date: Mapping[date, list[dict[str, Any]]],
        price_index: Mapping[tuple[str, date], Mapping[str, float]],
        metadata: Mapping[str, Any] | None = None,
    ) -> BacktestFrames:
        """5C 现实路径：OrderIntent → ExecutionSimulator + 双轨归因。"""
        from app.services.research_data.research_execution import (
            ResearchExecutionSimulator,
            build_attribution,
            resolve_market_bundle,
        )

        meta = dict(metadata or {})
        meta["_price_index"] = price_index
        bhash = compute_backtest_hash(spec)
        calendar = trading_calendar_from_bars(
            price_index, start=spec.start_date, end=spec.end_date
        )
        if not calendar:
            return BacktestFrames(
                backtest_hash=bhash,
                strategy_hash=spec.strategy_hash,
                metadata={"warning": "empty_calendar", "realism": "NET"},
            )

        exec_targets = map_targets_to_execution(
            targets_by_signal_date, calendar, spec.execution_policy
        )
        fill_field = spec.execution_policy.fill_field
        execution, price_pol, cost_pol, rules = resolve_market_bundle(
            spec.market_rule,
            research_fill_field=fill_field,
            research_delay_already_applied=True,
            cost_policy_override=meta.get("cost_policy_override"),
            trading_rule_override=meta.get("trading_rule_override"),
        )
        sim = ResearchExecutionSimulator(
            execution, rules, cost_pol, price_pol, calendar=calendar
        )

        # NET 账本
        cash = float(spec.initial_nav)
        shares: dict[str, float] = {}
        last_close: dict[str, float] = {}
        # GROSS 影子账本（无成本无约束）
        g_cash = float(spec.initial_nav)
        g_shares: dict[str, float] = {}
        g_last: dict[str, float] = {}

        nav_rows: list[NavPoint] = []
        ret_rows: list[DailyReturnRow] = []
        pos_rows: list[BacktestPositionRow] = []
        turn_rows: list[TurnoverRow] = []
        cost_rows: list[dict[str, Any]] = []
        fill_rows: list[dict[str, Any]] = []
        prev_nav: float | None = None
        first_rebalance = True
        trading_status = meta.get("trading_status_by_date") or {}

        for d in calendar:
            rebalanced = False
            turnover_val: float | None = None
            if d in exec_targets:
                targets = exec_targets[d]
                pre_nav = self._mark_nav(cash, shares, d, price_index, last_close)
                w_old = self._mv_weights(shares, d, price_index, last_close, pre_nav)
                if first_rebalance:
                    turnover_val = None
                    first_rebalance = False
                else:
                    keys = set(w_old) | set(targets)
                    turnover_val = 0.5 * sum(
                        abs(targets.get(k, 0.0) - w_old.get(k, 0.0)) for k in keys
                    )
                # GROSS 影子
                g_pre = self._mark_nav(g_cash, g_shares, d, price_index, g_last)
                g_cash, g_shares = self._rebalance(
                    g_pre, targets, d, price_index, fill_field
                )
                # NET 执行
                cash, shares, _step, cost_row, fills = sim.step_weights(
                    trading_date=d,
                    target_weights=targets,
                    cash=cash,
                    shares=shares,
                    price_index=price_index,
                    strategy_hash=spec.strategy_hash,
                    trading_status=trading_status,
                )
                cost_rows.append(cost_row.model_dump(mode="json"))
                fill_rows.extend(f.model_dump(mode="json") for f in fills)
                rebalanced = True

            turn_rows.append(
                TurnoverRow(
                    trading_date=d, turnover=turnover_val, rebalanced=rebalanced
                )
            )
            # 影子收盘
            g_nav, g_cash_m, _, _ = self._close_mark(
                g_cash, g_shares, d, price_index, g_last
            )
            g_cash = g_cash_m
            # NET 收盘
            nav, cash_mtm, gross, day_pos = self._close_mark(
                cash, shares, d, price_index, last_close
            )
            cash = cash_mtm
            nav_rows.append(
                NavPoint(trading_date=d, nav=nav, cash=cash, gross_exposure=gross)
            )
            pos_rows.extend(day_pos)
            pr: float | None = None
            if prev_nav is not None and prev_nav > 0:
                pr = nav / prev_nav - 1.0
            ret_rows.append(DailyReturnRow(trading_date=d, portfolio_return=pr))
            prev_nav = nav
            _ = g_nav  # 日终影子 NAV；终值用于归因

        from app.services.research_data.research_execution.protocol import DailyCostRow

        cost_models = [DailyCostRow.model_validate(r) for r in cost_rows]
        gross_final = (
            self._mark_nav(g_cash, g_shares, calendar[-1], price_index, g_last)
            if calendar
            else spec.initial_nav
        )
        net_final = nav_rows[-1].nav if nav_rows else spec.initial_nav
        attr = build_attribution(
            initial_nav=spec.initial_nav,
            gross_final_nav=gross_final,
            net_final_nav=net_final,
            cost_rows=cost_models,
        )

        frames = self._finalize_frames(
            spec,
            bhash=bhash,
            calendar=calendar,
            exec_targets=exec_targets,
            nav_rows=nav_rows,
            ret_rows=ret_rows,
            pos_rows=pos_rows,
            turn_rows=turn_rows,
            meta=meta,
            fill_field=fill_field,
            realism="NET",
        )
        metrics = dict(frames.metrics or {})
        metrics["attribution"] = attr.model_dump(mode="json")
        return frames.model_copy(
            update={
                "costs": cost_rows,
                "fills": fill_rows,
                "attribution": attr.model_dump(mode="json"),
                "metrics": metrics,
                "metadata": {
                    **dict(frames.metadata or {}),
                    "realism": "NET",
                    "market_rule": spec.market_rule,
                    "execution_profile_version": spec.execution_profile_version,
                    "unsupported_algorithms": list(sim.unsupported_algorithms),
                    "cost_policy": cost_pol.model_dump(mode="json"),
                    "trading_rule": rules.model_dump(mode="json"),
                },
            }
        )

    def _finalize_frames(
        self,
        spec: BacktestSpec,
        *,
        bhash: str,
        calendar: list[date],
        exec_targets: dict,
        nav_rows: list[NavPoint],
        ret_rows: list[DailyReturnRow],
        pos_rows: list[BacktestPositionRow],
        turn_rows: list[TurnoverRow],
        meta: dict[str, Any],
        fill_field: str,
        realism: str,
    ) -> BacktestFrames:
        bench = resolve_benchmark_returns(
            calendar,
            mode=spec.benchmark_mode,
            instrument_key=spec.benchmark_instrument_key,
            price_index={},  # filled below via meta/price in caller path
            metadata=meta,
        )
        # 重新用完整 price 需要调用方传入；此处从 meta 不取，改由下方重算
        # 实际上 attach 需要 price_index — 修复：从 run 传入
        # 为保持签名，benchmark 在各 run_* 末尾单独处理更清晰。
        # 这里用 meta["_price_index"] 可选注入。
        price_index = meta.get("_price_index")
        if price_index is not None:
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
                "realism": realism,
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
