"""从 Broker / Safety / Recon 等端口采集 ComponentHealth。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ..protocol import ComponentHealth, HealthStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def collect_broker_health(
    broker_port: Any = None,
    *,
    inject: Mapping[str, Any] | None = None,
) -> ComponentHealth:
    """Broker 连通性；断开 → DEGRADED（非 UNHEALTHY，除非 inject 强制）。"""
    inj = dict(inject or {})
    if inj.get("force_status"):
        st = str(inj["force_status"]).upper()
        return ComponentHealth(
            name="broker",
            status=st,  # type: ignore[arg-type]
            message=str(inj.get("message") or "injected"),
            checked_at=_now(),
        )
    connected = True
    if broker_port is not None:
        if hasattr(broker_port, "is_connected"):
            connected = bool(broker_port.is_connected())
        elif hasattr(broker_port, "_connected"):
            connected = bool(getattr(broker_port, "_connected", True))
    status: HealthStatus = "HEALTHY" if connected else "DEGRADED"
    msg = "connected" if connected else "broker disconnected"
    return ComponentHealth(name="broker", status=status, message=msg, checked_at=_now())


def collect_safety_health(
    safety_service: Any = None,
    account_id: str = "",
) -> ComponentHealth:
    """Safety 状态：blocked → DEGRADED。"""
    blocked = False
    reason = ""
    if safety_service is not None and account_id:
        try:
            blocked = bool(safety_service.is_blocked(account_id))
            if blocked:
                st = safety_service.get_state("ACCOUNT", account_id)
                reason = str(getattr(st, "reason", "") or "blocked")
        except Exception:
            blocked = True
            reason = "safety evaluate error"
    status: HealthStatus = "DEGRADED" if blocked else "HEALTHY"
    return ComponentHealth(
        name="safety",
        status=status,
        message=reason or ("normal" if not blocked else "trading blocked"),
        checked_at=_now(),
    )


def collect_reconciliation_health(
    *,
    recon_critical: bool = False,
    last_run_ok: Optional[bool] = None,
) -> ComponentHealth:
    """Recon CRITICAL 打开 → UNHEALTHY。"""
    if recon_critical:
        return ComponentHealth(
            name="reconciliation",
            status="UNHEALTHY",
            message="critical mismatch open",
            checked_at=_now(),
        )
    if last_run_ok is False:
        return ComponentHealth(
            name="reconciliation",
            status="DEGRADED",
            message="last run had findings",
            checked_at=_now(),
        )
    return ComponentHealth(
        name="reconciliation",
        status="HEALTHY",
        message="match",
        checked_at=_now(),
    )


def collect_oms_health(*, error_rate: float = 0.0) -> ComponentHealth:
    """OMS 简化的错误率启发式。"""
    if error_rate > 0.5:
        return ComponentHealth(
            name="oms",
            status="UNHEALTHY",
            message=f"high error rate {error_rate:.2f}",
            checked_at=_now(),
        )
    if error_rate > 0.05:
        return ComponentHealth(
            name="oms",
            status="DEGRADED",
            message=f"elevated error rate {error_rate:.2f}",
            checked_at=_now(),
        )
    return ComponentHealth(
        name="oms", status="HEALTHY", message="ok", checked_at=_now()
    )


def collect_market_data_health(
    *,
    max_age_sec: float = 0.0,
    stale_threshold_sec: float = 300.0,
) -> ComponentHealth:
    """行情陈旧 → DEGRADED。"""
    if max_age_sec > stale_threshold_sec:
        return ComponentHealth(
            name="market_data",
            status="DEGRADED",
            message=f"stale {max_age_sec:.0f}s",
            checked_at=_now(),
        )
    return ComponentHealth(
        name="market_data", status="HEALTHY", message="fresh", checked_at=_now()
    )


def collect_all(
    *,
    broker_port: Any = None,
    safety_service: Any = None,
    account_id: str = "",
    recon_critical: bool = False,
    inject: Mapping[str, Any] | None = None,
) -> list[ComponentHealth]:
    """默认采集集。"""
    return [
        collect_broker_health(broker_port, inject=inject),
        collect_oms_health(),
        collect_safety_health(safety_service, account_id),
        collect_reconciliation_health(recon_critical=recon_critical),
        collect_market_data_health(),
    ]
