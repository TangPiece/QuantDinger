"""Phase 7E：策略注册、版本钉扎与 LIVE 不可变校验。"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.strategy_registry.pin import content_hash_for_pin

from .protocol import StrategyLifecycleRecord, StrategyVersionPin


class VersionImmutableError(RuntimeError):
    """LIVE 版本禁止原地 mutate，须新版本重新走阶梯。"""


# content_hash_for_pin 已迁至 strategy_registry.pin（8A SSOT）；下方 re-export 供旧 import 路径。
__all__ = [
    "VersionImmutableError",
    "assert_version_immutable",
    "content_hash_for_pin",
    "new_lifecycle",
    "register_version_pin",
]


def register_version_pin(
    *,
    strategy_id: str,
    strategy_version: str,
    model_version: str = "",
    dataset_hash: str = "",
    feature_version: str = "",
    is_live: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> StrategyVersionPin:
    ch = content_hash_for_pin(
        strategy_version=strategy_version,
        model_version=model_version,
        dataset_hash=dataset_hash,
        feature_version=feature_version,
    )
    return StrategyVersionPin(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        model_version=model_version,
        dataset_hash=dataset_hash,
        feature_version=feature_version,
        content_hash=ch,
        is_live=is_live,
        metadata=dict(metadata or {}),
    )


def assert_version_immutable(
    pin: StrategyVersionPin,
    patch: Mapping[str, Any],
) -> None:
    """LIVE 钉扎版本若内容字段变化 → 拒。"""
    if not pin.is_live:
        return
    lock_fields = (
        "strategy_version",
        "model_version",
        "dataset_hash",
        "feature_version",
        "content_hash",
    )
    for key in lock_fields:
        if key not in patch:
            continue
        if patch[key] != getattr(pin, key, None):
            raise VersionImmutableError(f"{key} is immutable for LIVE strategy")


def new_lifecycle(strategy_id: str) -> StrategyLifecycleRecord:
    return StrategyLifecycleRecord(strategy_id=strategy_id, state="DRAFT")
