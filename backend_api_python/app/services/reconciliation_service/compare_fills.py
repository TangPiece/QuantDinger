"""Fill 对账：OMS fills（broker_execution_id）vs Snapshot.executions。"""

from __future__ import annotations

from typing import Any, Sequence

from .findings import make_finding
from .protocol import BrokerSnapshot, ReconciliationFinding


def _broker_exec_id(fill: Any) -> str:
    meta = dict(getattr(fill, "metadata", None) or {})
    return str(meta.get("broker_execution_id") or getattr(fill, "fill_id", "") or "")


def compare_fills(
    *,
    run_id: str,
    oms_fills: Sequence[Any],
    snapshot: BrokerSnapshot,
) -> list[ReconciliationFinding]:
    """缺 → MISSING_FILL；多 → UNEXPECTED_FILL；qty/price 差 → FILL_MISMATCH。"""
    findings: list[ReconciliationFinding] = []
    broker_by_eid = {
        str(e.broker_execution_id): e
        for e in (snapshot.executions or [])
        if e.broker_execution_id
    }
    # 同一 eid 只计一次（重复 execution 不双计）
    seen_internal: set[str] = set()

    for fill in oms_fills:
        eid = _broker_exec_id(fill)
        if not eid or eid in seen_internal:
            continue
        seen_internal.add(eid)
        qty = float(getattr(fill, "quantity", 0) or 0)
        px = float(getattr(fill, "price", 0) or 0)
        bro = broker_by_eid.get(eid)
        if bro is None:
            findings.append(
                make_finding(
                    run_id=run_id,
                    finding_type="MISSING_FILL",
                    severity="ERROR",
                    entity_type="FILL",
                    entity_id=eid,
                    expected={"broker_execution_id": eid, "quantity": qty, "price": px},
                    actual={},
                    difference={"missing_on_broker": True},
                )
            )
            continue
        diff: dict[str, Any] = {}
        if abs(qty - float(bro.quantity)) > 1e-6:
            diff["quantity"] = {"internal": qty, "broker": float(bro.quantity)}
        if abs(px - float(bro.price)) > 1e-6:
            diff["price"] = {"internal": px, "broker": float(bro.price)}
        if diff:
            findings.append(
                make_finding(
                    run_id=run_id,
                    finding_type="FILL_MISMATCH",
                    severity="ERROR",
                    entity_type="FILL",
                    entity_id=eid,
                    expected={"quantity": qty, "price": px},
                    actual={"quantity": float(bro.quantity), "price": float(bro.price)},
                    difference=diff,
                )
            )

    for eid, bro in broker_by_eid.items():
        if eid in seen_internal:
            continue
        findings.append(
            make_finding(
                run_id=run_id,
                finding_type="UNEXPECTED_FILL",
                severity="CRITICAL",
                entity_type="FILL",
                entity_id=eid,
                expected={},
                actual={
                    "broker_execution_id": eid,
                    "quantity": float(bro.quantity),
                    "price": float(bro.price),
                    "client_order_id": bro.client_order_id,
                },
                difference={"unexpected_on_broker": True},
            )
        )
    return findings
