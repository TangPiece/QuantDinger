"""Phase 6J：OMS 启动恢复 — 只查 Broker / apply_execution_report，禁止重下单。"""

from __future__ import annotations

from typing import Any, Callable

from .events import append_event
from .fill_bridge import bridge_fills_to_portfolio
from .protocol import Order, OutboxRecord, RecoverReport
from .reducer import apply_execution_report

# 终态订单：仅需清理 outbox，不向 Broker 再发单
_TERMINAL_STATUSES = frozenset(
    {
        "FILLED",
        "CANCELLED",
        "REJECTED",
        "BROKER_REJECTED",
        "REPLACED",
    }
)


def _query_broker_report(
    order: Order,
    *,
    broker_port: Any,
    broker_adapter_service: Any,
) -> Any:
    """向 Broker 查询订单状态；UNKNOWN 与 SUBMITTED 均走 query，不 submit。"""
    if broker_adapter_service is not None:
        return broker_adapter_service.recover_order(order)
    if hasattr(broker_port, "recover_unknown"):
        return broker_port.recover_unknown(order)  # type: ignore[attr-defined]
    if hasattr(broker_port, "get_order"):
        view = broker_port.get_order(client_order_id=order.client_order_id)
        from app.services.broker_adapter.execution_bridge import (
            order_view_to_execution_report,
        )

        return order_view_to_execution_report(
            order=order,
            broker_status=view.status,
            broker_order_id=view.broker_order_id,
            filled_quantity=view.filled_quantity,
            avg_price=view.avg_fill_price,
            broker=getattr(broker_port, "broker_id", "broker"),
        )
    raise RuntimeError("no broker query path for recovery")


def _apply_report(
    order: Order,
    report: Any,
    *,
    writer: Any,
    portfolio_service: Any,
) -> Order:
    """ExecutionReport → 持久化 + Portfolio bridge。"""
    events = []
    if str(report.status).upper() in (
        "FILL",
        "PARTIAL",
        "FILLED",
        "PARTIALLY_FILLED",
    ):
        if str(order.status) == "SUBMITTED":
            order, ev = append_event(
                order,
                event_type="ACKNOWLEDGED",
                new_status="ACKNOWLEDGED",
                source="BROKER",
                message="recover ack",
            )
            events.append(ev)
    order, more, fills = apply_execution_report(order, report)
    events.extend(more)
    writer.persist_order(order, events=events, fills=fills)
    if fills:
        bridge_fills_to_portfolio(
            order, fills, portfolio_service=portfolio_service
        )
    return order


def run_recover_on_start(
    *,
    writer: Any,
    outbox_drain: Callable[[Callable[[OutboxRecord], None], int], int],
    get_order: Callable[[str], Order],
    recover_unknown_fn: Callable[[str], Order],
    list_orders: Callable[..., list[Order]],
    broker_port: Any,
    broker_adapter_service: Any = None,
    portfolio_service: Any = None,
    account_id: str = "",
) -> RecoverReport:
    """扫描 SUBMITTED|UNKNOWN 与 PENDING outbox；禁止 port.submit / 重下单。"""
    report = RecoverReport(resubmit_attempted=False)
    pending_unknown: list[str] = []

    def _match_acct(order: Order) -> bool:
        if not account_id:
            return True
        return str(order.account_id or "") == account_id

    for order in list_orders(account_id=account_id):
        if not _match_acct(order):
            continue
        st = str(order.status)
        if st not in ("SUBMITTED", "UNKNOWN"):
            continue
        try:
            if st == "UNKNOWN":
                updated = recover_unknown_fn(order.order_id)
                if str(updated.status) == "UNKNOWN":
                    pending_unknown.append(order.order_id)
                else:
                    report.recovered_order_ids.append(order.order_id)
                continue
            br = _query_broker_report(
                order,
                broker_port=broker_port,
                broker_adapter_service=broker_adapter_service,
            )
            br_st = str(getattr(br, "status", "") or "").upper()
            if br_st in ("UNKNOWN", "") and not getattr(br, "fills", None):
                pending_unknown.append(order.order_id)
                continue
            updated = _apply_report(
                order,
                br,
                writer=writer,
                portfolio_service=portfolio_service,
            )
            if str(updated.status) != "UNKNOWN":
                report.recovered_order_ids.append(order.order_id)
            else:
                pending_unknown.append(order.order_id)
        except Exception as exc:
            report.errors.append(f"{order.order_id}: {exc}")

    def _outbox_handler(rec: OutboxRecord) -> None:
        if rec.event_type not in ("PAPER_SUBMIT", "BROKER_SUBMIT"):
            return
        oid = rec.aggregate_id or str(
            (rec.payload_json or {}).get("order_id") or ""
        )
        if not oid:
            return
        try:
            order = get_order(oid)
        except KeyError:
            return
        if not _match_acct(order):
            return
        if str(order.status) in _TERMINAL_STATUSES:
            return
        if str(order.status) == "UNKNOWN":
            recover_unknown_fn(oid)
            return
        br = _query_broker_report(
            order,
            broker_port=broker_port,
            broker_adapter_service=broker_adapter_service,
        )
        br_st = str(getattr(br, "status", "") or "").upper()
        if br_st in ("UNKNOWN", "") and not getattr(br, "fills", None):
            report.errors.append(
                f"outbox {rec.outbox_id}: broker has no state for {oid}"
            )
            return
        _apply_report(
            order,
            br,
            writer=writer,
            portfolio_service=portfolio_service,
        )
        if oid not in report.recovered_order_ids:
            report.recovered_order_ids.append(oid)

    try:
        outbox_drain(_outbox_handler, 500)
    except Exception as exc:
        report.errors.append(f"outbox_drain: {exc}")

    report.still_unknown = list(dict.fromkeys(pending_unknown))
    report.resubmit_attempted = False
    return report
