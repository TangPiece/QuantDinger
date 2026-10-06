"""ProductionBacktestEngine：逐日事件循环，组合 DataQuery + 3C ExecutionSimulator。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Mapping

from app.services.research_data.backtest.execution import (
    ExecutionSimulator,
    targets_to_order_intents,
)
from app.services.research_data.backtest.execution.models import MarketBar
from app.services.research_data.backtest.fingerprint import compute_request_fingerprint
from app.services.research_data.backtest.ledger import EquityPoint, PositionSnapshot, TradeRecord
from app.services.research_data.backtest.request import BacktestRequest
from app.services.research_data.backtest.result import BacktestResult
from app.services.research_data.backtest.version import BACKTEST_CONTRACT_VERSION
from app.services.research_data.contracts import PricePolicy, TargetPosition
from app.services.research_data.data_query import DataQuery
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import ProductionArtifactStore, compute_result_id
from .benchmark import build_benchmark_equity, summarize_vs_benchmark
from .market_loader import MarketPanel, load_market_panel, market_panel_from_bars
from .metrics import attach_drawdown, compute_metrics
from .portfolio_state import PortfolioState
from .signal_loader import load_targets_by_date, targets_for_day
from .version import PRODUCTION_BACKTEST_ENGINE_VERSION


class ProductionBacktestError(RuntimeError):
    """Production 回测失败。"""


class ProductionBacktestEngine:
    """实现 BacktestEngine Protocol：仅支持 engine=production。"""

    def __init__(
        self,
        query: DataQuery,
        registry: ResearchRegistry,
        *,
        artifact_store: ProductionArtifactStore | None = None,
    ) -> None:
        self._query = query
        self._registry = registry
        self._store = artifact_store or ProductionArtifactStore()

    def run(
        self,
        request: BacktestRequest,
        *,
        market_panel: MarketPanel | None = None,
        targets_by_date: dict[str, list[TargetPosition]] | None = None,
        bars_by_date: Mapping[str, Mapping[str, MarketBar]] | None = None,
    ) -> BacktestResult:
        """执行生产回测。

        Args:
            request: Domain BacktestRequest（engine=production）
            market_panel / bars_by_date / targets_by_date: 测试注入，跳过 DataQuery/artifact
        """
        if request.engine != "production":
            raise ProductionBacktestError(
                f"ProductionBacktestEngine only supports engine='production', got {request.engine!r}"
            )

        experiment = None
        snapshot_id = None
        try:
            experiment = self._registry.get_experiment(request.experiment_id)
            if experiment.dataset_hash != request.dataset_hash:
                raise ProductionBacktestError(
                    "dataset_hash mismatch: "
                    f"request={request.dataset_hash!r} experiment={experiment.dataset_hash!r}"
                )
            snapshot_id = experiment.snapshot_id
        except Exception as exc:
            # 允许测试用合成 experiment_id：仅当显式注入 targets 时
            if targets_by_date is None and bars_by_date is None and market_panel is None:
                raise ProductionBacktestError(f"experiment lookup failed: {exc}") from exc

        # --- targets ---
        if targets_by_date is None:
            artifact_id = request.target_positions_artifact_id
            if not artifact_id:
                raise ProductionBacktestError("target_positions_artifact_id is required")
            art = self._registry.get_artifact(artifact_id)
            targets_by_date = load_targets_by_date(
                art, start_date=request.start_date, end_date=request.end_date
            )

        # --- market panel ---
        if market_panel is None and bars_by_date is not None:
            market_panel = market_panel_from_bars(bars_by_date)
        if market_panel is None:
            instruments = sorted(
                {
                    t.instrument_key
                    for day_list in targets_by_date.values()
                    for t in day_list
                }
            )
            if request.benchmark and request.benchmark not in instruments:
                instruments.append(request.benchmark)
            if not instruments:
                # 无标的：空仓跑满日历需要至少能拿 calendar；用空 keys 则无日历
                instruments = []
            adj = request.market_price_policy.adjustment
            price_policy = PricePolicy(
                adjustment=adj if adj in ("none", "post", "pre") else "none"
            )
            start = date.fromisoformat(request.start_date[:10])
            end = date.fromisoformat(request.end_date[:10])
            if instruments:
                market_panel = load_market_panel(
                    self._query,
                    instrument_keys=instruments,
                    start=start,
                    end=end,
                    price_policy=price_policy,
                )
            else:
                market_panel = MarketPanel(calendar=[])

        calendar_dates = [
            d.isoformat()
            for d in market_panel.calendar
            if request.start_date[:10] <= d.isoformat() <= request.end_date[:10]
        ]
        # 若无行情日历但有信号日，用信号日并集保证可跑（测试注入）
        if not calendar_dates and targets_by_date:
            calendar_dates = sorted(targets_by_date.keys())

        state = PortfolioState(cash=float(request.initial_capital))
        sim = ExecutionSimulator(
            request.execution_policy,
            request.trading_rule,
            request.cost_policy,
            request.market_price_policy,
        )

        all_trades: list[TradeRecord] = []
        portfolio_history = []
        position_history: list[PositionSnapshot] = []
        equity_curve: list[EquityPoint] = []
        price_field = (
            "open"
            if request.execution_policy.execution_price == "open"
            else "close"
        )

        pending_intents = []  # 未到执行日的 intents 队列

        for day in calendar_dates:
            bars = market_panel.bars_for(day)
            # 信号日：生成 intents（T+delay 执行）
            day_targets = targets_for_day(targets_by_date, day)
            if day_targets:
                prices = {}
                for ik, bar in bars.items():
                    px = bar.open if price_field == "open" else bar.close
                    if px is not None:
                        prices[ik] = float(px)
                # 对无 bar 的目标用 close 占位价避免 qty=0（测试常给齐）
                port_in = state.to_input_snapshot(day)
                port_in = port_in.model_copy(
                    update={"total_value": state.to_snapshot(day, bars, price_field=price_field).total_value}
                )
                # 用面板日历解析 intended，与日循环对齐（避免节假日偏移）
                new_intents = targets_to_order_intents(
                    day_targets,
                    portfolio=port_in,
                    prices=prices,
                    execution_policy=request.execution_policy,
                    trading_rule=request.trading_rule,
                    portfolio_value=port_in.total_value,
                    calendar=market_panel.calendar,
                )
                pending_intents.extend(new_intents)

            # 仅执行 intended 落在本日的 intents
            due = []
            remain = []
            day_d = date.fromisoformat(day)
            for intent in pending_intents:
                if intent.intended_execution_time is not None:
                    if intent.intended_execution_time.date() == day_d:
                        due.append(intent)
                    elif intent.intended_execution_time.date() < day_d:
                        # 过期未成交：仍尝试（日历对齐后应少见）
                        due.append(intent)
                    else:
                        remain.append(intent)
                else:
                    due.append(intent)
            pending_intents = remain

            port_in = state.to_input_snapshot(day)
            step = sim.step(
                trading_date=day,
                intents=due,
                bars=bars,
                portfolio=port_in,
            )
            # 先记 realized（用 sync 前成本），再同步数量/现金
            filled = [t for t in step.trades if t.status in ("FILLED", "PARTIAL")]
            state.record_fills(filled)
            if step.portfolio is not None:
                state.sync_from_snapshot(step.portfolio)

            snap = state.to_snapshot(day, bars, price_field=price_field)
            # 禁止非法负现金（enforce_cash 下应已避免；防御断言写入 metadata）
            if snap.cash < -1e-6 and request.trading_rule.enforce_cash:
                raise ProductionBacktestError(
                    f"illegal negative cash {snap.cash} on {day}"
                )

            portfolio_history.append(snap)
            position_history.extend(snap.positions)
            all_trades.extend(step.trades)
            equity_curve.append(
                EquityPoint(
                    trading_date=day,
                    timestamp=datetime(day_d.year, day_d.month, day_d.day),
                    equity=float(snap.total_value),
                )
            )

        # 无交易日：至少保留初始权益点
        if not equity_curve:
            equity_curve = [
                EquityPoint(
                    trading_date=request.start_date[:10],
                    equity=float(request.initial_capital),
                    drawdown=0.0,
                )
            ]

        equity_curve = attach_drawdown(equity_curve)
        metrics = compute_metrics(
            equity_curve,
            trades=all_trades,
            initial_capital=request.initial_capital,
        )

        metadata: dict = {
            "engine": "production",
            "signal_artifact_id": request.target_positions_artifact_id,
            "dataset_ref": request.dataset_ref,
            "n_trading_days": len(calendar_dates),
            "n_trades_filled": sum(
                1 for t in all_trades if t.status in ("FILLED", "PARTIAL")
            ),
            "final_realized_pnl": state.realized_pnl,
            "final_total_cost": state.total_cost,
        }

        if request.benchmark:
            bench_curve = build_benchmark_equity(
                calendar_dates,
                market_panel.bars_by_date,
                benchmark_key=request.benchmark,
                initial_capital=request.initial_capital,
            )
            if bench_curve:
                metadata["benchmark"] = request.benchmark
                metadata["benchmark_summary"] = summarize_vs_benchmark(
                    equity_curve, bench_curve
                )

        fingerprint = compute_request_fingerprint(request)
        result_id = compute_result_id(fingerprint)
        result = BacktestResult(
            result_id=result_id,
            request_fingerprint=fingerprint,
            experiment_id=request.experiment_id,
            dataset_hash=request.dataset_hash,
            engine="production",
            engine_version=PRODUCTION_BACKTEST_ENGINE_VERSION,
            contract_version=request.contract_version or BACKTEST_CONTRACT_VERSION,
            equity_curve=equity_curve,
            trades=all_trades,
            position_history=position_history,
            portfolio_history=portfolio_history,
            metrics=metrics,
            artifact_uris={},
            metadata=metadata,
        )

        art = self._store.write_result(
            result, request=request, snapshot_id=snapshot_id
        )
        try:
            self._registry.upsert_artifact(art)
        except Exception:
            pass
        return result
