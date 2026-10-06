"""backtest_hash：钉住 strategy + 窗口 + 执行/基准/成本/引擎版本。"""

from __future__ import annotations

import hashlib
from typing import Any

from app.services.research_data.hashing import canonical_json

from .protocol import BacktestSpec


def _policy_fingerprint(spec: BacktestSpec) -> dict[str, Any]:
    """NET 时解析 MarketRule 费率/约束进 hash；GROSS 用空指纹。"""
    if spec.realism != "NET":
        return {"cost_policy": {}, "trading_rule": {}}
    from app.services.research_data.research_execution.market_rules import (
        fingerprint_policies,
        resolve_market_bundle,
    )

    meta = dict(spec.metadata or {})
    _e, _p, cost, rules = resolve_market_bundle(
        spec.market_rule,
        research_fill_field=spec.execution_policy.fill_field,
        research_delay_already_applied=True,
        cost_policy_override=meta.get("cost_policy_override"),
        trading_rule_override=meta.get("trading_rule_override"),
    )
    return fingerprint_policies(cost, rules)


def normalize_backtest_spec(spec: BacktestSpec) -> dict:
    """规范化 hash 输入（不含 metadata 注入数据）。"""
    fp = _policy_fingerprint(spec)
    return {
        "strategy_hash": spec.strategy_hash,
        "start_date": spec.start_date.isoformat(),
        "end_date": spec.end_date.isoformat(),
        "execution_policy": spec.execution_policy.mode,
        "benchmark_mode": spec.benchmark_mode,
        "benchmark_instrument_key": spec.benchmark_instrument_key or "",
        "initial_nav": float(spec.initial_nav),
        "missing_price_policy": spec.missing_price_policy,
        "exchange": spec.exchange or "CN",
        "realism": spec.realism,
        "market_rule": spec.market_rule if spec.realism == "NET" else "",
        "cost_enabled": bool(spec.cost_enabled),
        "execution_price_adjustment": spec.execution_price_adjustment,
        "execution_profile_version": spec.execution_profile_version,
        "cost_policy": fp.get("cost_policy") or {},
        "trading_rule": fp.get("trading_rule") or {},
        "engine_version": spec.engine_version,
        "return_calculation_version": spec.return_calculation_version,
    }


def compute_backtest_hash(spec: BacktestSpec) -> str:
    """稳定 backtest_hash。"""
    payload = normalize_backtest_spec(spec)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
