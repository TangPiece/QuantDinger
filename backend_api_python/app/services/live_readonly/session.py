"""Phase 7A：LiveReadonlySession 锁定 dataset/model/strategy 不可变。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from uuid import uuid4

from .hash import derive_session_id
from .protocol import LiveReadonlySession


class SessionImmutableError(RuntimeError):
    """尝试修改锁定字段。"""


_LOCK_FIELDS = frozenset({"dataset_hash", "model_version", "strategy_version"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_session(
    *,
    account_id: str,
    portfolio_id: str = "",
    trading_date: str = "",
    dataset_hash: str,
    model_version: str,
    strategy_version: str,
    salt: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> LiveReadonlySession:
    """创建 OPEN 会话并锁定三版本字段。"""
    sid = derive_session_id(
        account_id=account_id,
        dataset_hash=dataset_hash,
        model_version=model_version,
        strategy_version=strategy_version,
        salt=salt or str(uuid4())[:8],
    )
    return LiveReadonlySession(
        session_id=sid,
        environment="LIVE_READONLY",
        account_id=account_id,
        portfolio_id=portfolio_id,
        trading_date=trading_date,
        dataset_hash=dataset_hash,
        model_version=model_version,
        strategy_version=strategy_version,
        status="OPEN",
        opened_at=_now(),
        metadata=dict(metadata or {}),
    )


def assert_session_locked(
    session: LiveReadonlySession,
    *,
    dataset_hash: Optional[str] = None,
    model_version: Optional[str] = None,
    strategy_version: Optional[str] = None,
) -> None:
    """校验版本字段与已打开会话一致。"""
    if dataset_hash is not None and dataset_hash != session.dataset_hash:
        raise SessionImmutableError("dataset_hash locked for session")
    if model_version is not None and model_version != session.model_version:
        raise SessionImmutableError("model_version locked for session")
    if strategy_version is not None and strategy_version != session.strategy_version:
        raise SessionImmutableError("strategy_version locked for session")


def merge_session_update(
    session: LiveReadonlySession,
    patch: Mapping[str, Any],
) -> LiveReadonlySession:
    """允许更新 status/metadata；禁止改锁定字段。"""
    for key, val in patch.items():
        if key in _LOCK_FIELDS and val != getattr(session, key):
            raise SessionImmutableError(f"{key} is immutable")
    data = session.model_dump()
    for key, val in patch.items():
        if key in _LOCK_FIELDS:
            continue
        data[key] = val
    return LiveReadonlySession.model_validate(data)
