"""Phase 7D：Session / Daily 风险预算（env 配置）。"""

from __future__ import annotations

import os

from .protocol import ControlledSession, RiskBudget


def _parse_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    return float(raw)


def _parse_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    return int(raw)


def load_risk_budget_from_env() -> RiskBudget:
    """读取 CONTROLLED_LIVE_* / RISK_* 上限；CI 默认保守。"""
    return RiskBudget(
        max_orders=_parse_int("CONTROLLED_LIVE_MAX_ORDERS", 1),
        max_notional_session=_parse_float(
            "CONTROLLED_LIVE_MAX_NOTIONAL_SESSION",
            _parse_float("CONTROLLED_LIVE_MAX_NOTIONAL", 5000.0),
        ),
        max_turnover_session=_parse_float(
            "CONTROLLED_LIVE_MAX_TURNOVER_SESSION", 10000.0
        ),
        max_daily_loss=_parse_float("CONTROLLED_LIVE_MAX_DAILY_LOSS", 500.0),
        max_consecutive_rejects=_parse_int(
            "CONTROLLED_LIVE_MAX_CONSECUTIVE_REJECTS", 3
        ),
        max_consecutive_errors=_parse_int(
            "CONTROLLED_LIVE_MAX_CONSECUTIVE_ERRORS", 3
        ),
    )


def attach_risk_budget(session: ControlledSession) -> ControlledSession:
    """打开 session 时挂载 env 预算（保留已用计数）。"""
    base = load_risk_budget_from_env()
    rb = session.risk_budget
    merged = RiskBudget(
        max_orders=base.max_orders,
        max_notional_session=base.max_notional_session,
        max_turnover_session=base.max_turnover_session,
        max_daily_loss=base.max_daily_loss,
        max_consecutive_rejects=base.max_consecutive_rejects,
        max_consecutive_errors=base.max_consecutive_errors,
        session_notional_used=rb.session_notional_used,
        session_turnover_used=rb.session_turnover_used,
        consecutive_rejects=rb.consecutive_rejects,
        consecutive_errors=rb.consecutive_errors,
    )
    return session.model_copy(update={"risk_budget": merged})


def check_order_budget(
    session: ControlledSession, *, notional: float
) -> tuple[bool, str]:
    """校验单笔 notional + session 累计是否越界。"""
    rb = session.risk_budget
    cfg = session.config
    if session.order_count >= cfg.max_orders or session.order_count >= rb.max_orders:
        return False, "max_orders"
    if notional > cfg.max_notional:
        return False, "max_notional_per_order"
    projected = rb.session_notional_used + notional
    if projected > rb.max_notional_session:
        return False, "max_notional_session"
    if rb.session_turnover_used + notional > rb.max_turnover_session:
        return False, "max_turnover_session"
    if rb.consecutive_rejects >= rb.max_consecutive_rejects:
        return False, "consecutive_rejects"
    if rb.consecutive_errors >= rb.max_consecutive_errors:
        return False, "consecutive_errors"
    return True, ""


def record_order_submit(
    session: ControlledSession, *, notional: float, rejected: bool = False
) -> ControlledSession:
    """提交后更新 session 级累计（不自动加仓）。"""
    rb = session.risk_budget
    rejects = rb.consecutive_rejects + 1 if rejected else 0
    rb = rb.model_copy(
        update={
            "session_notional_used": rb.session_notional_used + notional,
            "session_turnover_used": rb.session_turnover_used + notional,
            "consecutive_rejects": rejects,
        }
    )
    return session.model_copy(update={"risk_budget": rb})


def record_runtime_error(session: ControlledSession) -> ControlledSession:
    """连续 runtime 错误计数，达上限由 stop_conditions 停机。"""
    rb = session.risk_budget
    rb = rb.model_copy(
        update={"consecutive_errors": rb.consecutive_errors + 1}
    )
    return session.model_copy(update={"risk_budget": rb})
