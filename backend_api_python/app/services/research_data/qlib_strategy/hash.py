"""qlib_run_hash：钉住 strategy + 窗口 + 执行/成本 + 物化缓存。"""

from __future__ import annotations

import hashlib
from typing import Any

from app.services.research_data.hashing import canonical_json

from .protocol import QlibStrategySpec


def _policy_fingerprint(spec: QlibStrategySpec) -> dict[str, Any]:
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


def normalize_qlib_strategy_spec(spec: QlibStrategySpec) -> dict:
    """规范化 hash 输入。"""
    fp = _policy_fingerprint(spec)
    return {
        "strategy_hash": spec.strategy_hash,
        "start_date": spec.start_date.isoformat(),
        "end_date": spec.end_date.isoformat(),
        "execution_policy": spec.execution_policy.mode,
        "realism": spec.realism,
        "market_rule": spec.market_rule if spec.realism == "NET" else "",
        "initial_nav": float(spec.initial_nav),
        "dataset_ref": spec.dataset_ref or "",
        "dataset_hash": spec.dataset_hash or "",
        "materialization_id": spec.materialization_id or "",
        "cost_policy": fp.get("cost_policy") or {},
        "trading_rule": fp.get("trading_rule") or {},
        "qlib_engine_version": spec.qlib_engine_version,
        "region": spec.region or "cn",
    }


def compute_qlib_run_hash(spec: QlibStrategySpec) -> str:
    """稳定 qlib_run_hash。"""
    payload = normalize_qlib_strategy_spec(spec)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
