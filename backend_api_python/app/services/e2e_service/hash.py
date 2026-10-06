"""Phase 6I：run / session / 指纹派生 id。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence


def derive_run_id(
    *,
    session_id: str = "",
    scenario_id: str = "",
    salt: str = "",
) -> str:
    """Suite 或单次运行的 run_id。"""
    raw = f"e2e|run|{session_id}|{scenario_id}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def derive_scenario_run_id(
    *,
    run_id: str,
    scenario_id: str,
    mode: str = "",
    salt: str = "",
) -> str:
    """幂等场景运行 id。"""
    raw = f"e2e|sc|{run_id}|{scenario_id}|{mode}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def derive_session_id(
    *,
    trading_date: str,
    market: str = "",
    mode: str = "PAPER",
    salt: str = "",
) -> str:
    """TradingSession 主键。"""
    raw = f"e2e|sess|{trading_date}|{market}|{mode}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def derive_virtual_order_id(
    *,
    scenario_run_id: str,
    instrument_key: str,
    side: str,
    quantity: float,
    salt: str = "",
) -> str:
    raw = f"e2e|vo|{scenario_run_id}|{instrument_key}|{side}|{quantity}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def derive_score_id(*, run_id: str, session_id: str = "") -> str:
    raw = f"e2e|score|{run_id}|{session_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def intent_fingerprint(intents: Sequence[Any]) -> str:
    """OrderIntent 列表确定性指纹（Replay 用）。"""
    rows: list[dict[str, Any]] = []
    for it in intents:
        if hasattr(it, "model_dump"):
            d = it.model_dump(mode="json")
        elif isinstance(it, dict):
            d = dict(it)
        else:
            d = {
                "instrument_key": getattr(it, "instrument_key", ""),
                "side": getattr(it, "side", ""),
                "quantity": getattr(it, "quantity", 0),
                "reason": getattr(it, "reason", ""),
            }
        rows.append(
            {
                "instrument_key": d.get("instrument_key"),
                "side": d.get("side"),
                "quantity": round(float(d.get("quantity") or 0), 8),
                "strategy_version": d.get("strategy_version"),
                "trace_id": d.get("trace_id"),
            }
        )
    rows.sort(key=lambda r: (str(r["instrument_key"]), str(r["side"])))
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
