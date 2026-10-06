"""production_bundle_hash：钉住研究身份 + 依赖锁。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .protocol import ENGINE_VERSION, ProductionBundleSpec


def normalize_production_bundle_spec(spec: ProductionBundleSpec) -> dict[str, Any]:
    """稳定序列化。"""
    lock = spec.dependency_lock.model_dump(mode="json")
    return {
        "strategy_hash": spec.strategy_hash,
        "cv_hash": spec.cv_hash,
        "backtest_hash": spec.backtest_hash or "",
        "qlib_run_hash": spec.qlib_run_hash or "",
        "dataset_hash": spec.dataset_hash or "",
        "materialization_id": spec.materialization_id or "",
        "feature_hashes": sorted(spec.feature_hashes or []),
        "processor_hash": spec.processor_hash or "",
        "pipeline_digest": spec.pipeline_digest or "",
        "model_artifact_id": spec.model_artifact_id or "",
        "model_version": spec.model_version or "",
        "universe_code": spec.universe_code or "",
        "snapshot_id": spec.snapshot_id or "",
        "execution_policy": spec.execution_policy or "NEXT_OPEN",
        "realism": spec.realism or "GROSS",
        "market_rule": spec.market_rule if spec.realism == "NET" else "",
        "dependency_lock": lock,
        "bundle_engine_version": spec.bundle_engine_version or ENGINE_VERSION,
    }


def compute_production_bundle_hash(spec: ProductionBundleSpec) -> str:
    """稳定 production bundle_hash（勿与 2A ResearchBundleIdentity 混淆）。"""
    payload = json.dumps(
        normalize_production_bundle_spec(spec),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
