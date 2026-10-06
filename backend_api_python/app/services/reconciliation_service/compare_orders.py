"""Order 对账：OMS list_orders vs Snapshot.open_orders（client_order_id）。"""

from __future__ import annotations

from typing import Any, Sequence

from .findings import make_finding
from .protocol import BrokerSnapshot, ReconciliationFinding


# OMS 终态不要求出现在 open_orders
_OMS_OPEN = frozenset(
    {"SUBMITTED", "ACKNOWLEDGED", "PARTIALLY_FILLED", "PENDING_CANCEL", "UNKNOWN"}
)


def compare_orders(
    *,
    run_id: str,
    oms_orders: Sequence[Any],
    snapshot: BrokerSnapshot,
) -> list[ReconciliationFinding]:
    """按 client_order_id 比对 side/qty/filled/status。"""
    findings: list[ReconciliationFinding] = []
    broker_by_clid = {
        str(o.client_order_id): o for o in (snapshot.open_orders or []) if o.client_order_id
    }
    seen_clid: set[str] = set()

    for order in oms_orders:
        clid = str(getattr(order, "client_order_id", "") or "")
        status = str(getattr(order, "status", "") or "")
        if not clid:
            continue
        seen_clid.add(clid)
        bro = broker_by_clid.get(clid)
        if bro is None:
            # 内部仍 open 但 broker 无 → MISSING_ORDER
            if status in _OMS_OPEN:
                findings.append(
                    make_finding(
                        run_id=run_id,
                        finding_type="MISSING_ORDER",
                        severity="ERROR",
                        entity_type="ORDER",
                        entity_id=clid,
                        expected={
                            "client_order_id": clid,
                            "status": status,
                            "quantity": float(getattr(order, "quantity", 0) or 0),
                        },
                        actual={},
                        difference={"missing_on_broker": True},
                    )
                )
            continue

        mismatches: dict[str, Any] = {}
        oq = float(getattr(order, "quantity", 0) or 0)
        of = float(getattr(order, "filled_quantity", 0) or 0)
        if abs(oq - float(bro.quantity)) > 1e-6:
            mismatches["quantity"] = {"internal": oq, "broker": float(bro.quantity)}
        if abs(of - float(bro.filled_quantity)) > 1e-6:
            mismatches["filled_quantity"] = {
                "internal": of,
                "broker": float(bro.filled_quantity),
            }
        oside = str(getattr(order, "side", "") or "")
        if oside and oside != str(bro.side):
            mismatches["side"] = {"internal": oside, "broker": bro.side}
        if mismatches:
            findings.append(
                make_finding(
                    run_id=run_id,
                    finding_type="ORDER_MISMATCH",
                    severity="ERROR",
                    entity_type="ORDER",
                    entity_id=clid,
                    expected={"quantity": oq, "filled": of, "side": oside, "status": status},
                    actual={
                        "quantity": float(bro.quantity),
                        "filled": float(bro.filled_quantity),
                        "side": bro.side,
                        "status": bro.status,
                    },
                    difference=mismatches,
                )
            )

    # Broker 有、OMS 无 → UNEXPECTED_ORDER（CRITICAL）
    for clid, bro in broker_by_clid.items():
        if clid in seen_clid:
            continue
        # 若 OMS 有同 clid 但已终态，不算 unexpected
        findings.append(
            make_finding(
                run_id=run_id,
                finding_type="UNEXPECTED_ORDER",
                severity="CRITICAL",
                entity_type="ORDER",
                entity_id=clid,
                expected={},
                actual={
                    "client_order_id": clid,
                    "quantity": float(bro.quantity),
                    "status": bro.status,
                    "instrument_key": bro.instrument_key,
                },
                difference={"unexpected_on_broker": True},
            )
        )
    return findings
