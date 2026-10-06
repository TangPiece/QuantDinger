"""backtest_hash：钉住 strategy + 窗口 + 执行/基准/引擎版本。"""

from __future__ import annotations

import hashlib

from app.services.research_data.hashing import canonical_json

from .protocol import BacktestSpec


def normalize_backtest_spec(spec: BacktestSpec) -> dict:
    """规范化 hash 输入（不含 metadata 注入数据）。"""
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
        "engine_version": spec.engine_version,
        "return_calculation_version": spec.return_calculation_version,
    }


def compute_backtest_hash(spec: BacktestSpec) -> str:
    """稳定 backtest_hash。"""
    payload = normalize_backtest_spec(spec)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
