"""Phase 6J：readiness run / scenario id 派生。"""

from __future__ import annotations

import hashlib


def derive_readiness_run_id(*, salt: str = "") -> str:
    """Checklist 运行 id。"""
    raw = f"rdy|run|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def derive_scenario_run_id(
    *,
    run_id: str,
    scenario_id: str,
    salt: str = "",
) -> str:
    raw = f"rdy|sc|{run_id}|{scenario_id}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
