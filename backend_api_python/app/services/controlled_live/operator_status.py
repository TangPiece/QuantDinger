"""Phase 7D：Operator 聚合状态 DTO（无完整 UI）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import Field

from app.services.research_data.contracts import _ContractModel

from .protocol import ControlledOrder, ControlledSession, ENGINE_VERSION


class OperatorStatusSnapshot(_ContractModel):
    """Session / 持仓 / 订单 / PnL / Safety / Recon 摘要。"""

    account_id: str = ""
    session: ControlledSession | None = None
    strategy_lock: dict[str, str] = Field(default_factory=dict)
    open_orders: list[ControlledOrder] = Field(default_factory=list)
    positions: list[dict[str, Any]] = Field(default_factory=list)
    daily_pnl: float = 0.0
    exposure: float = 0.0
    safety_state: str = "NORMAL"
    recon_critical_open: bool = False
    last_tick_at: str = ""
    alerts_summary: list[str] = Field(default_factory=list)
    engine_version: str = ENGINE_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_operator_status(
    *,
    session: ControlledSession | None,
    orders: list[ControlledOrder] | None = None,
    safety_state: str = "NORMAL",
    recon_critical_open: bool = False,
    daily_pnl: float = 0.0,
    exposure: float = 0.0,
    positions: list[dict[str, Any]] | None = None,
    last_tick_at: str = "",
    alerts: list[str] | None = None,
) -> OperatorStatusSnapshot:
    """从 ControlledLive / Runtime 内存视图聚合。"""
    sess = session
    lock: dict[str, str] = {}
    if sess is not None:
        lock = {
            "strategy_id": sess.approved_strategy_id,
            "strategy_version": sess.strategy_version,
            "model_version": sess.model_version,
            "dataset_hash": sess.dataset_hash,
            "feature_version": sess.feature_version,
            "processor_version": sess.processor_version,
            "snapshot_id": sess.snapshot_id,
        }
    open_orders = [
        o
        for o in (orders or [])
        if str(o.status).upper()
        not in ("FILLED", "REJECTED", "EXPIRED", "CANCELLED")
    ]
    alert_list = list(alerts or [])
    if sess and sess.stop_reason:
        alert_list.append(f"stop_reason={sess.stop_reason}")
    return OperatorStatusSnapshot(
        account_id=sess.account_id if sess else "",
        session=sess,
        strategy_lock=lock,
        open_orders=open_orders,
        positions=list(positions or []),
        daily_pnl=daily_pnl,
        exposure=exposure,
        safety_state=safety_state,
        recon_critical_open=recon_critical_open,
        last_tick_at=last_tick_at or datetime.now(timezone.utc).isoformat(),
        alerts_summary=alert_list,
    )
