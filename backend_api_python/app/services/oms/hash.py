"""order_id / client_order_id / idempotency / fill_id / event_id。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_idempotency_key(
    *,
    account_id: str,
    portfolio_id: str,
    instrument_key: str,
    side: str,
    quantity: float,
    risk_run_id: str = "",
    reason: str = "",
    salt: str = "",
) -> str:
    """同一 intent 只创建一个逻辑 Order（来自 reason / risk_run）。"""
    payload = {
        "account_id": account_id,
        "portfolio_id": portfolio_id,
        "instrument_key": instrument_key,
        "side": side,
        "quantity": round(float(quantity), 8),
        "risk_run_id": risk_run_id,
        "reason": reason,
        "salt": salt,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def derive_order_id(idempotency_key: str) -> str:
    return hashlib.sha256(f"oms|order|{idempotency_key}".encode("utf-8")).hexdigest()[
        :32
    ]


def derive_client_order_id(idempotency_key: str) -> str:
    return hashlib.sha256(
        f"oms|clid|{idempotency_key}".encode("utf-8")
    ).hexdigest()[:24]


def compute_fill_id(
    order_id: str, *, quantity: float, price: float, salt: str = ""
) -> str:
    raw = f"{order_id}|{quantity}|{price}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def compute_event_id(order_id: str, event_type: str, *, salt: str = "") -> str:
    raw = f"{order_id}|{event_type}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def compute_outbox_id(order_id: str, event_type: str, *, salt: str = "") -> str:
    raw = f"outbox|{order_id}|{event_type}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def compute_request_id(order_id: str, kind: str, *, salt: str = "") -> str:
    raw = f"req|{kind}|{order_id}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def stable_json(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
