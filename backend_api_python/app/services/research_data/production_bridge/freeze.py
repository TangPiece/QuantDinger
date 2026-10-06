"""Research → ProductionBundle 冻结（组装 Spec，不部署）。"""

from __future__ import annotations

import sys
from typing import Any, Mapping

from app.services.research_data.contracts import (
    CrossValidationSummary,
    StrategyResearchSummary,
)

from .hash import compute_production_bundle_hash
from .protocol import (
    ENGINE_VERSION,
    DependencyLock,
    ProductionBundleSpec,
)
from .state_machine import CV_PASS_STATUSES


class FreezeError(ValueError):
    """冻结失败。"""


def default_dependency_lock() -> DependencyLock:
    """冻结时记录运行时版本指纹。"""
    return DependencyLock(
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
        engine_versions={
            "production_bridge": ENGINE_VERSION,
            "strategy_research": "qd_strategy_research@1",
            "cross_validation": "qd_cross_validation@1",
            "research_backtest": "qd_research_backtest@1",
            "qlib_strategy": "qlib_strategy_adapter@1",
        },
        adapter_versions={"qlib_adapter": "qlib_adapter@2"},
    )


def build_bundle_spec(
    strategy: StrategyResearchSummary | None,
    cv: CrossValidationSummary,
    *,
    metadata: Mapping[str, Any] | None = None,
    require_cv_pass: bool = False,
) -> ProductionBundleSpec:
    """从 5A + 5E Summary 组装冻结 Spec。

    ``require_cv_pass=False`` 时允许 DRAFT 冻结（promote 时再门禁）。
    """
    meta = dict(metadata or {})
    if require_cv_pass and cv.status not in CV_PASS_STATUSES:
        raise FreezeError(f"cv status {cv.status!r} not freezeable with require_cv_pass")
    if strategy and strategy.strategy_hash != cv.strategy_hash:
        raise FreezeError("strategy_hash mismatch between strategy and cv")

    lock = default_dependency_lock()
    if meta.get("dependency_lock"):
        lock = DependencyLock.model_validate(meta["dependency_lock"])

    return ProductionBundleSpec(
        strategy_hash=cv.strategy_hash,
        cv_hash=cv.cv_hash,
        strategy_code=(
            (strategy.strategy_code if strategy else "")
            or str(meta.get("strategy_code") or cv.strategy_hash[:16])
        ),
        backtest_hash=cv.backtest_hash or str(meta.get("backtest_hash") or ""),
        qlib_run_hash=cv.qlib_run_hash or str(meta.get("qlib_run_hash") or ""),
        dataset_hash=str(meta.get("dataset_hash") or ""),
        materialization_id=str(meta.get("materialization_id") or ""),
        feature_hashes=list(meta.get("feature_hashes") or []),
        processor_hash=str(meta.get("processor_hash") or ""),
        processor_artifact_uri=str(meta.get("processor_artifact_uri") or ""),
        pipeline_digest=str(meta.get("pipeline_digest") or ""),
        model_artifact_id=str(meta.get("model_artifact_id") or ""),
        model_version=str(meta.get("model_version") or ""),
        universe_code=(
            (strategy.universe_code if strategy else "")
            or str(meta.get("universe_code") or "")
        ),
        snapshot_id=(
            (strategy.snapshot_id if strategy else "")
            or str(meta.get("snapshot_id") or "")
        ),
        execution_policy=cv.execution_policy or "NEXT_OPEN",
        realism=cv.realism or "GROSS",
        market_rule=str(meta.get("market_rule") or ""),
        parent_bundle_hash=str(meta.get("parent_bundle_hash") or ""),
        dependency_lock=lock,
        metadata={
            "signal_definition_json": (
                strategy.signal_definition_json if strategy else meta.get("signal_definition_json")
            )
            or {},
            "rebalance_rule_json": (
                strategy.rebalance_rule_json if strategy else meta.get("rebalance_rule_json")
            )
            or {},
            "holding_rule_json": (
                strategy.holding_rule_json if strategy else meta.get("holding_rule_json")
            )
            or {},
            **{
                k: meta[k]
                for k in ("factor_dataset_id", "portfolio_hash")
                if k in meta
            },
        },
    )


def freeze_identity(spec: ProductionBundleSpec) -> tuple[str, ProductionBundleSpec]:
    """计算 hash 并返回 (bundle_hash, spec)。"""
    return compute_production_bundle_hash(spec), spec
