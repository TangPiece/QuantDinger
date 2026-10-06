"""submit_intents → validate → outbox → PaperBroker → Fill → 6B bridge。"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from app.services.research_data.contracts import OrderIntent

from .cancel import apply_cancel
from .events import append_event
from .fill_bridge import bridge_fills_to_portfolio
from .intent_mapper import intent_to_order
from .outbox import make_outbox
from .paper_broker import PaperBroker
from .protocol import Fill, Order, OrderEvent, OutboxRecord, SubmitResult
from .reducer import apply_execution_report
from .replace import apply_replace
from .state_machine import StateMachineError
from .validation import ValidationError, validate_order


def run_submit_intents(
    intents: Sequence[OrderIntent],
    *,
    account_id: str,
    portfolio_id: str,
    risk_run_id: str = "",
    policy_hash: str = "",
    environment: str = "PAPER",
    writer: Any,
    paper_broker: PaperBroker,
    portfolio_service: Any = None,
    prices: Mapping[str, float] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> SubmitResult:
    """PAPER 路径主循环。"""
    if str(environment).upper() != "PAPER":
        raise StateMachineError("Phase 6D only supports environment=PAPER")

    if prices:
        paper_broker.set_prices(prices)

    meta = dict(metadata or {})
    orders: list[Order] = []
    all_fills: list[Fill] = []
    all_events: list[OrderEvent] = []
    outbox_ids: list[str] = []
    position_events: list[Any] = []

    for idx, intent in enumerate(intents):
        # 幂等：已存在则直接返回
        existing = writer.get_by_idempotency_for_intent(
            intent,
            account_id=account_id,
            portfolio_id=portfolio_id,
            risk_run_id=risk_run_id,
            salt=str(meta.get("idempotency_salt") or ""),
        )
        if existing is not None:
            orders.append(existing)
            continue

        order = intent_to_order(
            intent,
            account_id=account_id,
            portfolio_id=portfolio_id,
            risk_run_id=risk_run_id,
            policy_hash=policy_hash,
            idempotency_salt=str(meta.get("idempotency_salt") or ""),
            tif=meta.get("tif"),
            metadata={**meta, "intent_index": idx},
        )
        events: list[OrderEvent] = []

        # Validation
        try:
            validate_order(
                order,
                lot_size=float(meta.get("lot_size") or 1.0),
                tick_size=float(meta.get("tick_size") or 0.01),
                session_open=bool(meta.get("session_open", True)),
            )
            order, ev = append_event(
                order,
                event_type="VALIDATED",
                new_status="VALIDATED",
                message="validated",
            )
            events.append(ev)
        except ValidationError as exc:
            order, ev = append_event(
                order,
                event_type="REJECTED",
                new_status="REJECTED",
                message=str(exc),
            )
            events.append(ev)
            writer.persist_order(order, events=events, fills=[], outbox=None)
            orders.append(order)
            all_events.extend(events)
            continue

        # SUBMITTED + Outbox（同事务语义）
        order, ev = append_event(
            order,
            event_type="SUBMITTED",
            new_status="SUBMITTED",
            message="submitted to outbox",
        )
        events.append(ev)
        ob = make_outbox(
            order_id=order.order_id,
            event_type="PAPER_SUBMIT",
            payload={"order_id": order.order_id},
            salt=f"submit|{order.order_id}",
        )
        writer.persist_order(order, events=events, fills=[], outbox=ob)
        outbox_ids.append(ob.outbox_id)

        # 同步 Paper 路径（drain 也可异步；6D 默认同进程执行）
        report = paper_broker.submit(order)
        # ACK first if fill path
        if str(report.status).upper() in ("FILL", "PARTIAL", "FILLED", "PARTIALLY_FILLED"):
            if str(order.status) == "SUBMITTED":
                order, ev = append_event(
                    order,
                    event_type="ACKNOWLEDGED",
                    new_status="ACKNOWLEDGED",
                    source="BROKER",
                    message="paper ack before fill",
                    salt=f"preack|{order.order_id}",
                )
                events.append(ev)

        order, more_events, fills = apply_execution_report(order, report)
        events.extend(more_events)
        writer.persist_order(order, events=more_events, fills=fills, outbox=None)
        writer.mark_outbox(ob.outbox_id, "SENT")

        pos_evs = bridge_fills_to_portfolio(
            order,
            fills,
            portfolio_service=portfolio_service,
            writer=getattr(portfolio_service, "_writer", None)
            if portfolio_service
            else None,
        )
        position_events.extend(pos_evs)

        orders.append(order)
        all_fills.extend(fills)
        all_events.extend(events)

    return SubmitResult(
        orders=orders,
        fills=all_fills,
        events=all_events,
        outbox_ids=outbox_ids,
        position_events=position_events,
        metadata={
            "account_id": account_id,
            "portfolio_id": portfolio_id,
            "risk_run_id": risk_run_id,
            "policy_hash": policy_hash,
            "environment": environment,
            **meta,
        },
    )


def run_cancel(
    order: Order,
    *,
    reason: str = "",
    writer: Any,
    paper_broker: PaperBroker,
) -> Order:
    cur, events, req = apply_cancel(order, reason=reason, paper_broker=paper_broker)
    writer.persist_cancel(cur, events=events, request=req)
    return cur


def run_replace(
    order: Order,
    *,
    quantity: Optional[float] = None,
    limit_price: Optional[float] = None,
    writer: Any,
    paper_broker: PaperBroker,
) -> Order:
    cur, events, ver, req = apply_replace(
        order,
        quantity=quantity,
        limit_price=limit_price,
        paper_broker=paper_broker,
    )
    writer.persist_replace(cur, events=events, version=ver, request=req)
    return cur
