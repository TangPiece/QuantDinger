"""Phase 7C/7D：ControlledSession 打开、版本锁与 stop_reason。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

import hashlib

from .protocol import ControlledLiveConfig, ControlledSession, RiskBudget
from .risk_budget import attach_risk_budget, load_risk_budget_from_env


class SessionImmutableError(RuntimeError):
    """锁定字段变更必须 STOP 后新开 Session。"""


_LOCK_FIELDS = frozenset(
    {
        "dataset_hash",
        "model_version",
        "strategy_version",
        "approved_strategy_id",
        "feature_version",
        "processor_version",
        "snapshot_id",
        "environment",
        "account_id",
    }
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


def assert_session_immutable(
    session: ControlledSession, patch: Mapping[str, Any]
) -> None:
    """任何 hash/version 变更 → 拒，要求新 Session。"""
    for key, val in patch.items():
        if key not in _LOCK_FIELDS:
            continue
        if val != getattr(session, key, None):
            raise SessionImmutableError(f"{key} is immutable")


def halt_session(
    session: ControlledSession,
    *,
    stop_reason: str,
    status: str = "SAFETY_HOLD",
) -> ControlledSession:
    """写入 stop_reason 并进入 HALT/SAFETY_HOLD（仅拦新单）。"""
    return merge_session_update(
        session,
        {
            "status": status,
            "stop_reason": stop_reason,
            "runtime_phase": "HALTED",
        },
    )


def open_controlled_session(
    *,
    account_id: str,
    approved_strategy_id: str,
    dataset_hash: str,
    model_version: str,
    strategy_version: str,
    feature_version: str = "",
    processor_version: str = "",
    snapshot_id: str = "",
    config: ControlledLiveConfig | None = None,
    risk_budget: RiskBudget | None = None,
    effective_caps: Mapping[str, Any] | None = None,
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
    cfg = config or ControlledLiveConfig()
    rb = risk_budget or load_risk_budget_from_env()
    meta = dict(metadata or {})
    scale_level = ""
    if effective_caps:
        scale_level = str(effective_caps.get("scale_level") or "")
        meta["effective_caps"] = dict(effective_caps)
        # 7E：Session 打开时快照 governance caps，收紧 config / risk_budget
        max_n = float(effective_caps.get("max_notional_per_order") or 0)
        max_sess = float(effective_caps.get("max_notional_session") or 0)
        max_o = int(effective_caps.get("max_orders") or 0)
        if max_n > 0:
            cfg = cfg.model_copy(update={"max_notional": min(cfg.max_notional, max_n)})
        if max_o > 0:
            cfg = cfg.model_copy(update={"max_orders": min(cfg.max_orders, max_o)})
        if max_sess > 0:
            rb = rb.model_copy(
                update={"max_notional_session": min(rb.max_notional_session, max_sess)}
            )
        if max_o > 0:
            rb = rb.model_copy(update={"max_orders": min(rb.max_orders, max_o)})

    sess = ControlledSession(
        session_id=sid,
        account_id=account_id,
        environment="LIVE_CONTROLLED",
        approved_strategy_id=approved_strategy_id,
        dataset_hash=dataset_hash,
        model_version=model_version,
        strategy_version=strategy_version,
        feature_version=feature_version,
        processor_version=processor_version,
        snapshot_id=snapshot_id,
        status="OPEN",
        order_count=0,
        opened_at=datetime.now(timezone.utc).isoformat(),
        heartbeat_at=datetime.now(timezone.utc).isoformat(),
        runtime_phase="INIT",
        scale_level=scale_level,
        config=cfg,
        risk_budget=rb,
        metadata=meta,
    )
    return attach_risk_budget(sess)


def merge_session_update(
    session: ControlledSession, patch: Mapping[str, Any]
) -> ControlledSession:
    assert_session_immutable(session, patch)
    for key, val in patch.items():
        if key in _LOCK_FIELDS and val != getattr(session, key):
            raise SessionImmutableError(f"{key} is immutable")
    data = session.model_dump()
    for key, val in patch.items():
        if key in _LOCK_FIELDS:
            continue
        data[key] = val
    return ControlledSession.model_validate(data)
