"""Phase 8E：ExpectedBaseline 冻结与不可变校验。"""

from __future__ import annotations

from datetime import datetime, timezone

from .pin import baseline_content_hash
from .protocol import ExpectedBaseline, MetricsSnapshot


class BaselineImmutableError(RuntimeError):
    """禁止覆盖已冻结基线。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def assert_baseline_immutable(
    existing: ExpectedBaseline,
    *,
    metrics: MetricsSnapshot | None = None,
    content_hash: str | None = None,
) -> None:
    """已冻结 baseline 禁止改 metrics / content_hash。"""
    if not existing.immutable:
        return
    if metrics is not None:
        new_pin = baseline_content_hash(
            strategy_code=existing.strategy_code,
            strategy_version=existing.strategy_version,
            content_hash=existing.content_hash,
            pipeline_run_id=existing.pipeline_run_id,
            metrics=metrics,
        )
        old_pin = baseline_content_hash(
            strategy_code=existing.strategy_code,
            strategy_version=existing.strategy_version,
            content_hash=existing.content_hash,
            pipeline_run_id=existing.pipeline_run_id,
            metrics=existing.metrics_snapshot,
        )
        if new_pin != old_pin:
            raise BaselineImmutableError("ExpectedBaseline metrics are immutable after freeze")
    if content_hash is not None and str(content_hash) != str(existing.content_hash):
        raise BaselineImmutableError("ExpectedBaseline content_hash is immutable after freeze")


def build_frozen_baseline(
    *,
    baseline_id: str,
    strategy_code: str,
    strategy_version: str,
    content_hash: str,
    candidate_id: str,
    validation_id: str,
    pipeline_run_id: str,
    metrics: MetricsSnapshot,
    drift_policy_id: str,
    drift_policy_version: str,
    drift_policy_content_hash: str,
    dataset_hash: str = "",
    snapshot_id: str = "",
    model_version: str = "",
    feature_version: str = "",
    backtest_hash: str = "",
) -> ExpectedBaseline:
    return ExpectedBaseline(
        baseline_id=baseline_id,
        strategy_code=strategy_code,
        strategy_version=strategy_version,
        content_hash=content_hash,
        candidate_id=candidate_id,
        validation_id=validation_id,
        pipeline_run_id=pipeline_run_id,
        dataset_hash=dataset_hash,
        snapshot_id=snapshot_id,
        model_version=model_version,
        feature_version=feature_version,
        backtest_hash=backtest_hash,
        baseline_type="PROMOTION_BASELINE",
        metrics_snapshot=metrics,
        drift_policy_id=drift_policy_id,
        drift_policy_version=drift_policy_version,
        drift_policy_content_hash=drift_policy_content_hash,
        immutable=True,
        created_at=_now(),
    )


__all__ = [
    "BaselineImmutableError",
    "assert_baseline_immutable",
    "build_frozen_baseline",
]
