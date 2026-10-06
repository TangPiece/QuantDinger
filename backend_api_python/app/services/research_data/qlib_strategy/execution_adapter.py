"""5C MarketRule / Cost → Qlib exchange_kwargs + Compatibility。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.backtest.policy import (
    BacktestMarketPricePolicy,
    CostPolicy,
    ExecutionPolicy,
    TradingRule,
)
from app.services.research_data.backtest.request import BacktestRequest
from app.services.research_data.backtest_qlib.exchange_map import map_exchange_kwargs
from app.services.research_data.research_execution.market_rules import (
    resolve_market_bundle,
)

from .compatibility import assess_compatibility
from .protocol import CompatibilityReport, QlibStrategySpec


def resolve_execution_bundle(
    spec: QlibStrategySpec,
) -> tuple[ExecutionPolicy, BacktestMarketPricePolicy, CostPolicy, TradingRule]:
    """解析 5C 市场规则包（研究层已映射 delay → T+0）。"""
    meta = dict(spec.metadata or {})
    if spec.realism == "GROSS":
        # 零成本 / 宽松规则，对齐 5B GROSS
        execution = ExecutionPolicy(
            signal_time_rule="close_of_signal_day",
            execution_delay="T+0",
            execution_price=spec.execution_policy.fill_field,  # type: ignore[arg-type]
            execution_mode="market",
        )
        price = BacktestMarketPricePolicy(
            adjustment="none",
            reference_price=spec.execution_policy.fill_field  # type: ignore[arg-type]
            if spec.execution_policy.fill_field in ("open", "close")
            else "close",
            corporate_action_mode="ignore",
        )
        return execution, price, CostPolicy(), TradingRule(
            lot_size=1,
            t_plus=0,
            limit_up_down=False,
            short_allowed=True,
            fractional_shares=True,
            enforce_cash=False,
        )
    return resolve_market_bundle(
        spec.market_rule,
        research_fill_field=spec.execution_policy.fill_field,
        research_delay_already_applied=True,
        cost_policy_override=meta.get("cost_policy_override"),
        trading_rule_override=meta.get("trading_rule_override"),
    )


def build_exchange_kwargs(spec: QlibStrategySpec) -> dict[str, Any]:
    """Domain 政策 → Qlib Exchange kwargs（复用 3B map_exchange_kwargs）。"""
    execution, price, cost, rules = resolve_execution_bundle(spec)
    # 构造最小 BacktestRequest 供 map_exchange_kwargs
    req = BacktestRequest(
        experiment_id="qlib_strategy_adapter",
        dataset_hash=spec.dataset_hash or "injected",
        strategy_version=spec.qlib_engine_version,
        start_date=spec.start_date.isoformat(),
        end_date=spec.end_date.isoformat(),
        initial_capital=float(spec.initial_nav),
        engine="qlib",
        execution_policy=execution,
        market_price_policy=price,
        cost_policy=cost,
        trading_rule=rules,
        dataset_ref=spec.dataset_ref or None,
    )
    return map_exchange_kwargs(req)


def build_compatibility(spec: QlibStrategySpec) -> CompatibilityReport:
    """CompatibilityReport 门面。"""
    return assess_compatibility(spec)
