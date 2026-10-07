"""Phase 7C：ControlledSession 打开与锁定字段。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

import hashlib

from .protocol import ControlledLiveConfig, ControlledSession


class SessionImmutableError(RuntimeError):
    pass


_LOCK_FIELDS = frozenset(
    {"dataset_hash", "model_version", "strategy_version", "approved_strategy_id"}
)


def derive_controlled_session_id(
    *,
    account_id: str,
    dataset_hash: str,
    model_version: str,
    strategy_version: str,
    salt: str = "",
) -> str:
    raw = "|".join([account_id, dataset_hash, model_version, strategy_version, salt])
    return "cls_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def open_controlled_session(
    *,
    account_id: str,
    approved_strategy_id: str,
    dataset_hash: str,
    model_version: str,
    strategy_version: str,
    config: ControlledLiveConfig | None = None,
    salt: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> ControlledSession:
    sid = derive_controlled_session_id(
        account_id=account_id,
        dataset_hash=dataset_hash,
        model_version=model_version,
        strategy_version=strategy_version,
        salt=salt or str(uuid4())[:8],
    )
    return ControlledSession(
        session_id=sid,
        account_id=account_id,
        environment="LIVE_CONTROLLED",
        approved_strategy_id=approved_strategy_id,
        dataset_hash=dataset_hash,
        model_version=model_version,
        strategy_version=strategy_version,
        status="OPEN",
        order_count=0,
        opened_at=datetime.now(timezone.utc).isoformat(),
        config=config or ControlledLiveConfig(),
        metadata=dict(metadata or {}),
    )


def merge_session_update(
    session: ControlledSession, patch: Mapping[str, Any]
) -> ControlledSession:
    for key, val in patch.items():
        if key in _LOCK_FIELDS and val != getattr(session, key):
            raise SessionImmutableError(f"{key} is immutable")
    data = session.model_dump()
    for key, val in patch.items():
        if key in _LOCK_FIELDS:
            continue
        data[key] = val
    return ControlledSession.model_validate(data)
