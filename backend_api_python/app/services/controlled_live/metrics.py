"""Phase 7D：Controlled Live 低基数 metrics helpers。"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.ops_service.metrics.counters import MetricsRegistry, increment_counter


def _registry(ops: Any | None) -> MetricsRegistry | None:
    if ops is None:
        return None
    try:
        return ops.metrics
    except Exception:
        reg = getattr(ops, "_metrics", None)
        return reg if isinstance(reg, MetricsRegistry) else None


def record_tick(
    ops: Any | None,
    *,
    account_id: str = "",
    latency_ms: float = 0.0,
) -> None:
    reg = _registry(ops)
    if reg is None:
        return
    labels = {"account": account_id} if account_id else None
    increment_counter(reg, "controlled_live_tick_total", labels=labels)
    if latency_ms > 0:
        increment_counter(
            reg,
            "controlled_live_tick_latency_ms",
            value=latency_ms,
            labels=labels,
        )


def record_order_submitted(ops: Any | None, *, account_id: str = "") -> None:
    reg = _registry(ops)
    if reg is None:
        return
    increment_counter(
        reg,
        "controlled_live_orders_submitted",
        labels={"account": account_id} if account_id else None,
    )


def record_order_terminal(
    ops: Any | None, *, account_id: str = "", status: str = ""
) -> None:
    reg = _registry(ops)
    if reg is None:
        return
    st = str(status or "").upper()
    name = "controlled_live_orders_filled"
    if st == "REJECTED":
        name = "controlled_live_orders_rejected"
    elif st not in ("FILLED", "REJECTED"):
        return
    increment_counter(
        reg,
        name,
        labels={"account": account_id} if account_id else None,
    )


def record_md_stale(ops: Any | None, *, account_id: str = "") -> None:
    reg = _registry(ops)
    if reg is None:
        return
    increment_counter(
        reg,
        "controlled_live_md_stale_total",
        labels={"account": account_id} if account_id else None,
    )


def record_recon_mismatch(ops: Any | None, *, account_id: str = "") -> None:
    reg = _registry(ops)
    if reg is None:
        return
    increment_counter(
        reg,
        "controlled_live_recon_mismatch_total",
        labels={"account": account_id} if account_id else None,
    )


def record_risk_breach(ops: Any | None, *, account_id: str = "", reason: str = "") -> None:
    reg = _registry(ops)
    if reg is None:
        return
    _ = reason
    increment_counter(
        reg,
        "controlled_live_risk_breach_total",
        labels={"account": account_id} if account_id else None,
    )


def record_shadow_drift(
    ops: Any | None,
    *,
    account_id: str = "",
    metric: str = "return",
    value: float = 0.0,
) -> None:
    """累计日级 drift（counter 近似；详细 artifact 见 writers）。"""
    reg = _registry(ops)
    if reg is None:
        return
    name = f"controlled_live_shadow_drift_{metric}"
    increment_counter(
        reg,
        name,
        value=max(value, 0.0) or 1.0,
        labels={"account": account_id} if account_id else None,
    )


def snapshot_metrics(ops: Any | None) -> Mapping[str, float]:
    reg = _registry(ops)
    if reg is None:
        return {}
    return reg.snapshot()
