"""BacktestRequest 内容指纹。"""

from __future__ import annotations

import hashlib

from app.services.research_data.hashing import canonical_json

from .request import BacktestRequest
from .version import BACKTEST_CONTRACT_VERSION


def _request_payload(request: BacktestRequest, *, include_engine: bool) -> dict:
    """构造指纹 payload；Phase 3E 语义指纹排除 engine。"""
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
        "seed": request.seed,
        "execution_policy": request.execution_policy.model_dump(mode="json"),
        "market_price_policy": request.market_price_policy.model_dump(mode="json"),
        "cost_policy": request.cost_policy.model_dump(mode="json"),
        "trading_rule": request.trading_rule.model_dump(mode="json"),
    }
    if include_engine:
        payload["engine"] = request.engine
    return payload


def compute_request_fingerprint(request: BacktestRequest) -> str:
    """同请求（含 engine）→ 同 fingerprint（不含 result_id）。"""
    return hashlib.sha256(
        canonical_json(_request_payload(request, include_engine=True)).encode("utf-8")
    ).hexdigest()


def compute_semantic_fingerprint(request: BacktestRequest) -> str:
    """跨引擎可比语义指纹：同政策/信号/区间，排除 engine。"""
    return hashlib.sha256(
        canonical_json(_request_payload(request, include_engine=False)).encode("utf-8")
    ).hexdigest()
