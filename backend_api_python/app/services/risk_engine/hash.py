"""policy_hash / risk_run_id / idempotency_key。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence


def compute_policy_hash(policy: Any) -> str:
    """稳定策略哈希（不含 policy_hash 自身）。"""
    if hasattr(policy, "model_dump"):
        d = policy.model_dump(mode="json")
    else:
        d = dict(policy)
    d.pop("policy_hash", None)
    d.pop("metadata", None)
    raw = json.dumps(d, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_idempotency_key(
    *,
    account_id: str,
    portfolio_id: str,
    trading_date: str,
    apply_id: str,
    policy_hash: str,
    deltas_fingerprint: str,
) -> str:
    payload = {
        "account_id": account_id,
        "portfolio_id": portfolio_id,
        "trading_date": trading_date,
        "apply_id": apply_id,
        "policy_hash": policy_hash,
        "deltas": deltas_fingerprint,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def derive_risk_run_id(idempotency_key: str) -> str:
    return hashlib.sha256(f"risk|{idempotency_key}".encode("utf-8")).hexdigest()[:32]


def deltas_fingerprint(deltas: Sequence[Any]) -> str:
    rows = []
    for d in deltas:
        if hasattr(d, "model_dump"):
            x = d.model_dump(mode="json")
        else:
            x = dict(d)
        rows.append(
            {
                "instrument_key": str(x.get("instrument_key") or ""),
                "delta_quantity": x.get("delta_quantity"),
                "target_weight": x.get("target_weight"),
                "side": x.get("side"),
            }
        )
    rows.sort(key=lambda r: r["instrument_key"])
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def compute_event_id(risk_run_id: str, rule_code: str, *, salt: str = "") -> str:
    raw = f"{risk_run_id}|{rule_code}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
