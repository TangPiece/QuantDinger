"""account_id / portfolio_id / event_id / snapshot_id / idempotency_key。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence


def compute_account_id(
    *, environment: str, market: str, salt: str
) -> str:
    payload = "|".join([environment, market, salt, "qd_portfolio_service@1"])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_portfolio_id(*, account_id: str, runtime_id: str = "", label: str = "default") -> str:
    payload = "|".join([account_id, runtime_id or "", label, "qd_portfolio_service@1"])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def compute_event_id(
    *,
    portfolio_id: str,
    event_type: str,
    instrument_key: str = "",
    salt: str = "",
) -> str:
    raw = f"{portfolio_id}|{event_type}|{instrument_key}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def compute_snapshot_id(
    *,
    portfolio_id: str,
    trading_date: str,
    knowledge_time: str = "",
) -> str:
    raw = f"{portfolio_id}|{trading_date}|{knowledge_time}|snap"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def compute_apply_idempotency_key(
    *,
    account_id: str,
    portfolio_id: str,
    trading_date: str,
    runtime_id: str = "",
    run_id: str = "",
    targets_fingerprint: str = "",
) -> str:
    """同一 runtime run + 目标集重复 apply → 短路。"""
    payload = {
        "account_id": account_id,
        "portfolio_id": portfolio_id,
        "trading_date": trading_date,
        "runtime_id": runtime_id or "",
        "run_id": run_id or "",
        "targets": targets_fingerprint or "",
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def derive_apply_id(idempotency_key: str) -> str:
    return hashlib.sha256(f"apply|{idempotency_key}".encode("utf-8")).hexdigest()[:32]


def targets_fingerprint(targets: Sequence[Any]) -> str:
    rows = []
    for t in targets:
        if hasattr(t, "model_dump"):
            d = t.model_dump(mode="json")
        elif isinstance(t, dict):
            d = t
        else:
            d = {"repr": str(t)}
        rows.append(
            {
                "instrument_key": str(d.get("instrument_key") or ""),
                "target_weight": d.get("target_weight"),
                "target_quantity": d.get("target_quantity"),
            }
        )
    rows.sort(key=lambda x: x["instrument_key"])
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
