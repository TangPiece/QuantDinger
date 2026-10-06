"""幂等：同一 idempotency_key 重复 tick 返回已有 run。"""

from __future__ import annotations

from typing import Any

from app.services.research_data.contracts import ProductionRuntimeRunSummary

from .hash import compute_idempotency_key, derive_run_id


def build_idempotency_key(
    *,
    bundle_hash: str,
    trading_date: str,
    session_phase: str,
    decision_bucket: str,
    instruments: list[str] | None = None,
    signal_version: str = "",
) -> str:
    return compute_idempotency_key(
        bundle_hash=bundle_hash,
        trading_date=trading_date,
        session_phase=session_phase,
        decision_bucket=decision_bucket,
        instruments=instruments,
        signal_version=signal_version,
    )


def lookup_run(
    registry: Any, idempotency_key: str
) -> ProductionRuntimeRunSummary | None:
    """命中 registry 则返回已有 run；未实现方法时返回 None。"""
    getter = getattr(registry, "get_runtime_run_by_idempotency", None)
    if getter is None:
        return None
    try:
        return getter(idempotency_key)
    except KeyError:
        return None
    except Exception:
        return None


def new_run_id(idempotency_key: str) -> str:
    return derive_run_id(idempotency_key)
