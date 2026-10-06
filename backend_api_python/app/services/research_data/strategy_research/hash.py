"""strategy_hash：钉住因子/组合/规则/快照。"""

from __future__ import annotations

import hashlib

from app.services.research_data.hashing import canonical_json

from .protocol import StrategySpec


def normalize_strategy_spec(
    spec: StrategySpec, *, factor_dataset_hash: str
) -> dict:
    """规范化 hash 输入。"""
    sig = spec.signal_definition
    assert sig is not None
    return {
        "strategy_code": spec.strategy_code,
        "factor_dataset_id": spec.factor_dataset_id,
        "factor_dataset_hash": factor_dataset_hash,
        "portfolio_hash": spec.portfolio_hash,
        "signal_definition": sig.model_dump(mode="json"),
        "rebalance_rule": spec.rebalance_rule.model_dump(mode="json"),
        "holding_rule": spec.holding_rule.model_dump(mode="json"),
        "universe_code": spec.universe_code or "",
        "snapshot_id": spec.snapshot_id or "",
        "timing_profile": spec.timing_profile,
        "strategy_version": spec.strategy_version,
    }


def compute_strategy_hash(
    spec: StrategySpec, *, factor_dataset_hash: str
) -> str:
    """稳定 strategy_hash。"""
    payload = normalize_strategy_spec(spec, factor_dataset_hash=factor_dataset_hash)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
