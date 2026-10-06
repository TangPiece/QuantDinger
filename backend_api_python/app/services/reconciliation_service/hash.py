"""run_id / finding_id / snapshot_id 派生。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def derive_run_id(
    account_id: str,
    *,
    mode: str,
    salt: str = "",
) -> str:
    """稳定派生 ReconciliationRun.run_id。"""
    raw = f"recon|run|{account_id}|{mode}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def derive_snapshot_id(
    broker_id: str,
    account_id: str,
    *,
    captured_at: str,
    salt: str = "",
) -> str:
    """BrokerSnapshot.snapshot_id。"""
    raw = f"recon|snap|{broker_id}|{account_id}|{captured_at}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def derive_finding_id(
    run_id: str,
    *,
    finding_type: str,
    entity_id: str,
    salt: str = "",
) -> str:
    """Finding 幂等 id（同 run 同 type+entity 唯一）。"""
    raw = f"recon|find|{run_id}|{finding_type}|{entity_id}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def checksum_payload(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def stable_json(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
