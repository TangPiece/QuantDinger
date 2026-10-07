"""Phase 7E：Rollback 到 previous stable immutable version（新 session，非原地改 LIVE）。"""

from __future__ import annotations

from datetime import datetime, timezone

from .protocol import StrategyLifecycleRecord, StrategyVersionPin
from .strategy_registry import register_version_pin


class RollbackError(RuntimeError):
    pass


def rollback_strategy_version(
    lifecycle: StrategyLifecycleRecord,
    pin: StrategyVersionPin,
    *,
    to_version: str,
    previous_pin: StrategyVersionPin | None,
) -> tuple[StrategyLifecycleRecord, StrategyVersionPin]:
    """切回旧 version：lifecycle→PAUSED/SHADOW 由调用方决定；此处钉扎旧版本并清 LIVE 标记。"""
    if not to_version:
        raise RollbackError("to_version required")
    if previous_pin is None or previous_pin.strategy_version != to_version:
        raise RollbackError(f"stable version {to_version!r} not found")

    # 回滚后不得保持 LIVE 态（须新 session 重新走审批阶梯）
    new_lc = lifecycle.model_copy(
        update={
            "state": "PAUSED" if lifecycle.state == "LIVE" else lifecycle.state,
            "active_version": to_version,
            "previous_stable_version": pin.strategy_version,
            "scale_level": "L1_CONTROLLED",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                **dict(lifecycle.metadata or {}),
                "rollback_from": pin.strategy_version,
            },
        }
    )
    new_pin = register_version_pin(
        strategy_id=previous_pin.strategy_id,
        strategy_version=previous_pin.strategy_version,
        model_version=previous_pin.model_version,
        dataset_hash=previous_pin.dataset_hash,
        feature_version=previous_pin.feature_version,
        is_live=False,
        metadata={"rollback_target": True},
    )
    return new_lc, new_pin
