"""OrderIntent（research）→ Order draft。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from app.services.research_data.contracts import OrderIntent

from .hash import (
    compute_idempotency_key,
    derive_client_order_id,
    derive_order_id,
)
from .protocol import ENGINE_VERSION, Order


def _map_order_type(algo: str) -> str:
    a = str(algo or "MARKET").upper()
    if a == "LIMIT":
        return "LIMIT"
    # TWAP/VWAP/POV 等 6D 不支持执行算法；降级为 MARKET
    return "MARKET"


def _map_tif(urgency: str, *, explicit: Optional[str] = None) -> str:
    if explicit:
        return str(explicit).upper()
    u = str(urgency or "NORMAL").upper()
    if u == "HIGH":
        return "IOC"
    if u == "LOW":
        return "GTC"
    return "DAY"


def intent_to_order(
    intent: OrderIntent,
    *,
    account_id: str,
    portfolio_id: str,
    risk_run_id: str = "",
    policy_hash: str = "",
    idempotency_salt: str = "",
    tif: Optional[str] = None,
    metadata: Mapping[str, Any] | None = None,
) -> Order:
    """将 6C OrderIntent 映射为 CREATED Order。"""
    reason = str(intent.reason or "")
    idem = compute_idempotency_key(
        account_id=account_id,
        portfolio_id=portfolio_id,
        instrument_key=intent.instrument_key,
        side=str(intent.side),
        quantity=float(intent.quantity),
        risk_run_id=risk_run_id,
        reason=reason,
        salt=idempotency_salt,
    )
    now = datetime.now(timezone.utc).isoformat()
    order_type = _map_order_type(str(intent.execution_algorithm))
    meta = dict(metadata or {})
    meta.setdefault("intent_reason", reason)
    meta.setdefault("signal_id", intent.signal_id)
    meta.setdefault("urgency", intent.urgency)
    # Phase 6H：trace 写入 Order.metadata 供 Fill/审计关联
    tid = str(getattr(intent, "trace_id", "") or "").strip()
    if tid:
        meta.setdefault("trace_id", tid)
    return Order(
        order_id=derive_order_id(idem),
        client_order_id=derive_client_order_id(idem),
        account_id=account_id,
        portfolio_id=portfolio_id,
        risk_run_id=risk_run_id,
        policy_hash=policy_hash,
        instrument_key=intent.instrument_key,
        side=str(intent.side),  # type: ignore[arg-type]
        order_type=order_type,  # type: ignore[arg-type]
        tif=_map_tif(str(intent.urgency), explicit=tif),  # type: ignore[arg-type]
        quantity=float(intent.quantity),
        limit_price=float(intent.limit_price)
        if intent.limit_price is not None
        else None,
        status="CREATED",
        version=1,
        idempotency_key=idem,
        trading_date=str(intent.trading_date or ""),
        engine_version=ENGINE_VERSION,
        created_at=now,
        updated_at=now,
        metadata=meta,
    )
