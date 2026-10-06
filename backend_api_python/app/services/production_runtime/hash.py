"""runtime_id / idempotency_key / run_id。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence


def compute_runtime_id(
    *,
    bundle_hash: str,
    environment: str,
    market: str,
    started_bucket: str,
) -> str:
    """稳定 runtime_id（含启动日桶，避免永久碰撞）。"""
    payload = "|".join(
        [bundle_hash, environment, market, started_bucket, "qd_production_runtime@1"]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_idempotency_key(
    *,
    bundle_hash: str,
    trading_date: str,
    session_phase: str,
    decision_bucket: str,
    instruments: Sequence[str] | None = None,
    signal_version: str = "",
) -> str:
    """幂等键：同决策桶重复 tick 返回已有 run。"""
    inst_fp = ",".join(sorted(str(x) for x in (instruments or [])))
    payload = {
        "bundle_hash": bundle_hash,
        "trading_date": trading_date,
        "session_phase": session_phase,
        "decision_bucket": decision_bucket,
        "instruments": inst_fp,
        "signal_version": signal_version or "",
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def derive_run_id(idempotency_key: str) -> str:
    """run_id 由幂等键派生（可复现）。"""
    return hashlib.sha256(f"run|{idempotency_key}".encode("utf-8")).hexdigest()[:32]


def instrument_fingerprint(instruments: Sequence[str] | None) -> str:
    return hashlib.sha256(
        ",".join(sorted(str(x) for x in (instruments or []))).encode("utf-8")
    ).hexdigest()[:16]
