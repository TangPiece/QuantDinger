"""BacktestRequest 内容指纹。"""

from __future__ import annotations

import hashlib

from app.services.research_data.hashing import canonical_json

from .request import BacktestRequest
from .version import BACKTEST_CONTRACT_VERSION


def compute_request_fingerprint(request: BacktestRequest) -> str:
    """同请求语义 → 同 fingerprint（不含 result_id）。"""
    payload = {
        "contract_version": request.contract_version or BACKTEST_CONTRACT_VERSION,
        "experiment_id": request.experiment_id,
        "dataset_hash": request.dataset_hash,
        "dataset_ref": request.dataset_ref,
        "strategy_version": request.strategy_version,
        "signal_run_id": request.signal_run_id,
        "target_positions_artifact_id": request.target_positions_artifact_id,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "universe_code": request.universe_code,
        "initial_capital": request.initial_capital,
        "benchmark": request.benchmark,
        "frequency": request.frequency,
        "engine": request.engine,
        "seed": request.seed,
        "execution_policy": request.execution_policy.model_dump(mode="json"),
        "market_price_policy": request.market_price_policy.model_dump(mode="json"),
        "cost_policy": request.cost_policy.model_dump(mode="json"),
        "trading_rule": request.trading_rule.model_dump(mode="json"),
    }
    return hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()
