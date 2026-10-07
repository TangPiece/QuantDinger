"""Phase 7D：tick 前/后停机条件 → HaltDecision。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .protocol import ControlledSession
from .risk_budget import load_risk_budget_from_env


@dataclass(frozen=True)
class HaltDecision:
    """是否应 STOP NEW ORDERS 并写入 stop_reason。"""

    halt: bool
    stop_reason: str = ""
    status: str = "SAFETY_HOLD"


def _md_health(md: Any | None) -> Mapping[str, Any]:
    if md is None:
        return {"connected": True, "stale": False, "age_sec": 0.0}
    if hasattr(md, "health"):
        try:
            return dict(md.health() or {})
        except Exception:
            return {"connected": False, "stale": True, "age_sec": 9999.0}
    return {"connected": True, "stale": False, "age_sec": 0.0}


def _broker_health(broker: Any | None) -> Mapping[str, Any]:
    if broker is None:
        return {"connected": True}
    if hasattr(broker, "is_connected"):
        try:
            return {"connected": bool(broker.is_connected())}
        except Exception:
            return {"connected": False}
    return {"connected": True}


def pre_tick(
    session: ControlledSession,
    *,
    md: Any | None = None,
    broker: Any | None = None,
    safety_state: str = "NORMAL",
) -> HaltDecision:
    """MD stale/disconnect、broker disconnect、Safety HALT/EMERGENCY。"""
    if session.status in ("HALTED", "CLOSED", "SAFETY_HOLD"):
        return HaltDecision(True, session.stop_reason or session.status, session.status)

    st = str(safety_state or "NORMAL").upper()
    if st in ("HALTED", "EMERGENCY"):
        return HaltDecision(True, f"safety_{st.lower()}", "SAFETY_HOLD")
    if st == "DEGRADED":
        # DEGRADED：拦新单，session 仍可观察（不强制 SAFETY_HOLD）
        return HaltDecision(True, "safety_degraded", "OPEN")

    mh = _md_health(md)
    if not mh.get("connected", True):
        return HaltDecision(True, "md_disconnect", "SAFETY_HOLD")
    if mh.get("stale"):
        return HaltDecision(True, "md_stale", "SAFETY_HOLD")

    bh = _broker_health(broker)
    if not bh.get("connected", True):
        return HaltDecision(True, "broker_disconnect", "SAFETY_HOLD")

    return HaltDecision(False)


def post_tick(
    session: ControlledSession,
    *,
    daily_pnl: float = 0.0,
    recon_critical: bool = False,
    unknown_orders: int = 0,
) -> HaltDecision:
    """日亏、对账 CRITICAL、UNKNOWN 订单、连续错误。"""
    rb = session.risk_budget
    budget = load_risk_budget_from_env()
    max_loss = rb.max_daily_loss or budget.max_daily_loss
    if daily_pnl <= -abs(max_loss):
        return HaltDecision(True, "daily_loss_limit", "SAFETY_HOLD")

    if recon_critical:
        return HaltDecision(True, "recon_mismatch", "SAFETY_HOLD")

    if unknown_orders > 0:
        return HaltDecision(True, "unknown_order", "SAFETY_HOLD")

    if rb.consecutive_errors >= rb.max_consecutive_errors:
        return HaltDecision(True, "consecutive_errors", "SAFETY_HOLD")

    if rb.consecutive_rejects >= rb.max_consecutive_rejects:
        return HaltDecision(True, "consecutive_rejects", "SAFETY_HOLD")

    return HaltDecision(False)


def apply_halt_to_session(
    session: ControlledSession, decision: HaltDecision
) -> ControlledSession:
    """将 HaltDecision 合并进 session（含 stop_reason）。"""
    if not decision.halt:
        return session
    from .session import merge_session_update

    patch: dict[str, Any] = {
        "stop_reason": decision.stop_reason,
        "runtime_phase": "HALTED",
    }
    if decision.status != "OPEN":
        patch["status"] = decision.status
    return merge_session_update(session, patch)
