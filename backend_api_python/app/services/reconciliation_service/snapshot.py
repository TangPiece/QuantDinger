"""BrokerAdapter → BrokerSnapshot（compare 唯一外部入口）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from app.services.broker_adapter.protocol import (
    BrokerAccountView,
    BrokerOrderView,
    BrokerPositionView,
)

from .hash import checksum_payload, derive_snapshot_id
from .protocol import BrokerExecutionView, BrokerSnapshot


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collect_executions(adapter: Any, *, inject: Mapping[str, Any]) -> list[BrokerExecutionView]:
    """从 Simulated.recent_executions 或 adapter metadata 收集成交。"""
    drop = bool(inject.get("drop_execution_from_snapshot"))
    drop_ids = set(inject.get("drop_execution_ids") or [])
    out: list[BrokerExecutionView] = []
    raw_list: list[dict[str, Any]] = []
    rest = getattr(adapter, "_rest", None)
    if rest is not None and hasattr(rest, "recent_executions"):
        raw_list = list(rest.recent_executions(limit=500))
    elif hasattr(adapter, "recent_executions"):
        raw_list = list(adapter.recent_executions(limit=500))

    for ex in raw_list:
        eid = str(ex.get("broker_execution_id") or "")
        if drop and eid:
            continue
        if eid in drop_ids:
            continue
        out.append(
            BrokerExecutionView(
                broker_execution_id=eid,
                client_order_id=str(ex.get("client_order_id") or ""),
                order_id=str(ex.get("order_id") or ""),
                quantity=float(ex.get("quantity") or 0),
                price=float(ex.get("price") or 0),
                fee=float(ex.get("fee") or 0),
                ts=str(ex.get("ts") or ""),
                metadata=dict(ex.get("metadata") or {}),
            )
        )

    # 故障注入：额外 unexpected execution
    for extra in inject.get("inject_executions") or []:
        out.append(
            BrokerExecutionView.model_validate(dict(extra))
            if not isinstance(extra, BrokerExecutionView)
            else extra
        )
    return out


def build_broker_snapshot(
    adapter: Any,
    *,
    account_id: str,
    broker_id: str = "",
    inject: Mapping[str, Any] | None = None,
    raw_storage_uri: str = "",
    salt: str = "",
) -> BrokerSnapshot:
    """调用 adapter.get_account/positions/open_orders + executions → Snapshot。

    inject 支持 Simulated 故障：
    - force_broker_position: {instrument_key: qty}
    - force_broker_cash: float
    - drop_execution_from_snapshot / drop_execution_ids
    - inject_open_orders / inject_executions
    """
    inj = dict(inject or {})
    bid = broker_id or str(getattr(adapter, "broker_id", "") or "unknown")
    captured = _now()
    snap_id = derive_snapshot_id(bid, account_id, captured_at=captured, salt=salt)

    account = adapter.get_account()
    if not isinstance(account, BrokerAccountView):
        account = BrokerAccountView.model_validate(dict(account))
    if inj.get("force_broker_cash") is not None:
        account = account.model_copy(
            update={"cash": float(inj["force_broker_cash"]), "equity": float(inj["force_broker_cash"])}
        )

    positions = list(adapter.get_positions() or [])
    typed_pos: list[BrokerPositionView] = []
    for p in positions:
        typed_pos.append(
            p if isinstance(p, BrokerPositionView) else BrokerPositionView.model_validate(dict(p))
        )
    force_pos = inj.get("force_broker_position")
    if isinstance(force_pos, Mapping):
        typed_pos = [
            BrokerPositionView(
                instrument_key=str(k),
                quantity=float(v),
                available_quantity=float(v),
                side="LONG" if float(v) >= 0 else "SHORT",
            )
            for k, v in force_pos.items()
        ]

    open_orders = list(adapter.get_open_orders() or [])
    typed_oo: list[BrokerOrderView] = []
    for o in open_orders:
        typed_oo.append(
            o if isinstance(o, BrokerOrderView) else BrokerOrderView.model_validate(dict(o))
        )
    for extra in inj.get("inject_open_orders") or []:
        typed_oo.append(
            extra
            if isinstance(extra, BrokerOrderView)
            else BrokerOrderView.model_validate(dict(extra))
        )

    executions = _collect_executions(adapter, inject=inj)

    snap = BrokerSnapshot(
        snapshot_id=snap_id,
        broker_id=bid,
        account_id=account_id,
        captured_at=captured,
        account=account.model_copy(update={"account_id": account_id or account.account_id}),
        positions=typed_pos,
        open_orders=typed_oo,
        executions=executions,
        raw_storage_uri=raw_storage_uri,
        metadata={"checksum": checksum_payload({"positions": typed_pos, "executions": executions})},
    )
    return snap
