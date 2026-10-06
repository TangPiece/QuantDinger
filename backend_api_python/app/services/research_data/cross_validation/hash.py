"""cv_hash：钉住 strategy + 配对引擎 + 窗口 + 容差。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .protocol import CrossValidationSpec, ENGINE_VERSION


def normalize_cv_spec(spec: CrossValidationSpec) -> dict[str, Any]:
    """稳定序列化用于 hash。"""
    tol = spec.tolerances.model_dump(mode="json")
    return {
        "strategy_hash": spec.strategy_hash,
        "start_date": spec.start_date.isoformat(),
        "end_date": spec.end_date.isoformat(),
        "backtest_hash": spec.backtest_hash or "",
        "qlib_run_hash": spec.qlib_run_hash or "",
        "execution_policy": spec.execution_policy.mode,
        "realism": spec.realism,
        "market_rule": spec.market_rule if spec.realism == "NET" else "",
        "initial_nav": float(spec.initial_nav),
        "tolerances": tol,
        "cv_engine_version": spec.cv_engine_version or ENGINE_VERSION,
    }


def compute_cv_hash(spec: CrossValidationSpec) -> str:
    """稳定 cv_hash。"""
    payload = json.dumps(
        normalize_cv_spec(spec), sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
