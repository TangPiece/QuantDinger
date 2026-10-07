"""Phase 7B：ShadowSession 锁定 dataset/model/strategy。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

import hashlib

from .protocol import ShadowSession


class SessionImmutableError(RuntimeError):
    pass


_LOCK_FIELDS = frozenset({"dataset_hash", "model_version", "strategy_version"})


def derive_shadow_session_id(
    *,
    account_id: str,
    dataset_hash: str,
    model_version: str,
    strategy_version: str,
    salt: str = "",
) -> str:
    raw = "|".join([account_id, dataset_hash, model_version, strategy_version, salt])
    return "shs_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def open_shadow_session(
    *,
    account_id: str,
    dataset_hash: str,
    model_version: str,
    strategy_version: str,
    salt: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> ShadowSession:
    sid = derive_shadow_session_id(
        account_id=account_id,
        dataset_hash=dataset_hash,
        model_version=model_version,
        strategy_version=strategy_version,
        salt=salt or str(uuid4())[:8],
    )
    return ShadowSession(
        session_id=sid,
        account_id=account_id,
        environment="SHADOW",
        dataset_hash=dataset_hash,
        model_version=model_version,
        strategy_version=strategy_version,
        status="OPEN",
        opened_at=datetime.now(timezone.utc).isoformat(),
        metadata=dict(metadata or {}),
    )


def merge_session_update(session: ShadowSession, patch: Mapping[str, Any]) -> ShadowSession:
    for key, val in patch.items():
        if key in _LOCK_FIELDS and val != getattr(session, key):
            raise SessionImmutableError(f"{key} is immutable")
    data = session.model_dump()
    for key, val in patch.items():
        if key in _LOCK_FIELDS:
            continue
        data[key] = val
    return ShadowSession.model_validate(data)
