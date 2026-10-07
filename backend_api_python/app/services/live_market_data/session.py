"""Phase 7B：LiveMdSession 锁定 dataset/model/strategy 不可变。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from .hash import derive_md_session_id
from .protocol import LiveMdSession


class SessionImmutableError(RuntimeError):
    """尝试修改锁定字段。"""


_LOCK_FIELDS = frozenset({"dataset_hash", "model_version", "strategy_version"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_md_session(
    *,
    feed_id: str,
    account_id: str = "",
    dataset_hash: str,
    model_version: str,
    strategy_version: str,
    salt: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> LiveMdSession:
    sid = derive_md_session_id(
        feed_id=feed_id,
        account_id=account_id,
        dataset_hash=dataset_hash,
        model_version=model_version,
        strategy_version=strategy_version,
        salt=salt or str(uuid4())[:8],
    )
    return LiveMdSession(
        session_id=sid,
        feed_id=feed_id,
        account_id=account_id,
        dataset_hash=dataset_hash,
        model_version=model_version,
        strategy_version=strategy_version,
        status="OPEN",
        opened_at=_now(),
        metadata=dict(metadata or {}),
    )


def assert_session_locked(
    session: LiveMdSession,
    *,
    dataset_hash: str | None = None,
    model_version: str | None = None,
    strategy_version: str | None = None,
) -> None:
    if dataset_hash is not None and dataset_hash != session.dataset_hash:
        raise SessionImmutableError("dataset_hash locked for session")
    if model_version is not None and model_version != session.model_version:
        raise SessionImmutableError("model_version locked for session")
    if strategy_version is not None and strategy_version != session.strategy_version:
        raise SessionImmutableError("strategy_version locked for session")


def merge_session_update(
    session: LiveMdSession,
    patch: Mapping[str, Any],
) -> LiveMdSession:
    for key, val in patch.items():
        if key in _LOCK_FIELDS and val != getattr(session, key):
            raise SessionImmutableError(f"{key} is immutable")
    data = session.model_dump()
    for key, val in patch.items():
        if key in _LOCK_FIELDS:
            continue
        data[key] = val
    return LiveMdSession.model_validate(data)
