"""submit_intents → validate → outbox → BrokerPort → Fill → 6B bridge。"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from app.services.research_data.contracts import OrderIntent

from .broker_port import BrokerPort
from .cancel import apply_cancel
from .events import append_event
from .fill_bridge import bridge_fills_to_portfolio
from .intent_mapper import intent_to_order
from .outbox import make_outbox
from .paper_broker import PaperBroker
from .protocol import Fill, Order, OrderEvent, SubmitResult
from .reducer import apply_execution_report
from .replace import apply_replace
from .state_machine import StateMachineError
from .validation import ValidationError, validate_order

_ALLOWED_ENV = frozenset({"PAPER", "SANDBOX", "SHADOW", "ALPACA_PAPER"})


def _ops_audit_order(
    ops_service: Any,
    *,
    event_type: str,
    order: Any,
    account_id: str,
    strategy_id: str = "",
    reason: str = "",
) -> None:
    """6H：OMS 侧审计 + 低基数 metrics。"""
    if ops_service is None:
        return
    meta = dict(getattr(order, "metadata", None) or {})
    trace_id = str(meta.get("trace_id") or "")
    broker = str(meta.get("broker_id") or meta.get("environment") or "")
    try:
        ops_service.emit_audit(
            event_type=event_type,
            trace_id=trace_id,
            account_id=account_id,
            strategy_id=strategy_id,
            order_id=str(getattr(order, "order_id", "") or ""),
            entity_type="order",
            entity_id=str(getattr(order, "order_id", "") or ""),
            reason=reason,
            salt=str(getattr(order, "order_id", "") or event_type),
        )
        counter = {
            "ORDER_SUBMIT": "orders_submitted_total",
            "ORDER_CANCEL": "orders_cancelled_total",
            "EXECUTION_RECEIVED": "fills_total",
        }.get(event_type)
        if counter:
            ops_service.record_order_metric(
                counter,
                broker=broker,
                account=account_id,
                strategy=strategy_id,
            )
    except Exception:
        pass


class TradingGateBlocked(ValidationError):
    """6G Safety / 6F Recon：Fail-Closed 阻断新 submit。"""


def _apply_report_to_order(
    order: Order,
    report: Any,
    *,
    writer: Any,
    portfolio_service: Any,
    events: list,
) -> tuple[Order, list, list]:
    """ExecutionReport → state + fills + position bridge。"""
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
                message="ack before fill",
                salt=f"preack|{order.order_id}",
            )
            events.append(ev)
    order, more_events, fills = apply_execution_report(order, report)
    events.extend(more_events)
    writer.persist_order(order, events=more_events, fills=fills, outbox=None)
    bridge_fills_to_portfolio(
        order,
        fills,
        portfolio_service=portfolio_service,
        writer=getattr(portfolio_service, "_writer", None)
        if portfolio_service
        else None,
    )
    return order, more_events, fills


def run_submit_intents(
    intents: Sequence[OrderIntent],
    *,
    account_id: str,
    portfolio_id: str,
    risk_run_id: str = "",
    policy_hash: str = "",
    environment: str = "PAPER",
    writer: Any,
    broker_port: BrokerPort,
    portfolio_service: Any = None,
    prices: Mapping[str, float] | None = None,
    metadata: Mapping[str, Any] | None = None,
    # 兼容旧调用方
    paper_broker: Any = None,
    trading_gate: Any = None,
    ops_service: Any = None,
) -> SubmitResult:
    """PAPER 默认同步；SANDBOX/SHADOW 或 async_submit → BROKER_SUBMIT outbox。"""
    meta_pre = dict(metadata or {})
    strategy_id = str(meta_pre.get("strategy_id") or "")
    first_intent = intents[0] if intents else None
    # 6G Safety Gate（Fail-Closed）；cancel/recover 不走此路径
    if trading_gate is not None:
        blocked = True
        block_reason = "safety gate unavailable (fail-closed)"
        try:
            if hasattr(trading_gate, "decide"):
                decision = trading_gate.decide(
                    account_id,
                    intent=first_intent,
                    strategy_id=strategy_id,
                    prices=prices,
                )
                blocked = str(getattr(decision, "decision", "ALLOW")).upper() != "ALLOW"
                block_reason = (
                    getattr(decision, "reason", "") or block_reason
                )
            elif hasattr(trading_gate, "is_blocked"):
                blocked = bool(trading_gate.is_blocked(account_id))
                block_reason = "trading gate blocked"
            else:
                blocked = False
        except Exception as exc:
            blocked = True
            block_reason = f"safety gate error (fail-closed): {exc}"
        if blocked:
            if ops_service is not None:
                try:
                    from app.services.ops_service.trace import trace_id_from_intent

                    ops_service.notify_safety_block(
                        account_id,
                        reason=block_reason,
                        strategy_id=strategy_id,
                        trace_id=trace_id_from_intent(first_intent)
                        if first_intent
                        else "",
                    )
                except Exception:
                    pass
            raise TradingGateBlocked(
                f"trading blocked for account {account_id}: {block_reason}"
            )

    env = str(environment).upper()
    if env not in _ALLOWED_ENV:
        raise StateMachineError(
            f"environment must be one of {sorted(_ALLOWED_ENV)}, got {environment!r}"
        )
    if env == "LIVE":
        raise StateMachineError("LIVE not enabled in Phase 6E")

    port: BrokerPort = broker_port or paper_broker or PaperBroker()
    if prices and hasattr(port, "set_prices"):
        port.set_prices(prices)

    meta = dict(metadata or {})
    async_submit = bool(meta.get("async_submit")) or env in (
        "SANDBOX",
        "SHADOW",
        "ALPACA_PAPER",
    )
    # PAPER 默认同步（6D 兼容）；可用 async_submit 强制 outbox-only
    if env == "PAPER" and not meta.get("async_submit"):
        async_submit = False

    outbox_event = "BROKER_SUBMIT" if async_submit or env != "PAPER" else "PAPER_SUBMIT"
    if env == "PAPER" and not async_submit:
        outbox_event = "PAPER_SUBMIT"

    orders: list[Order] = []
    all_fills: list[Fill] = []
    all_events: list[OrderEvent] = []
    outbox_ids: list[str] = []
    position_events: list[Any] = []

    for idx, intent in enumerate(intents):
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

        order, ev = append_event(
            order,
            event_type="SUBMITTED",
            new_status="SUBMITTED",
            message="submitted to outbox",
        )
        events.append(ev)
        ob = make_outbox(
            order_id=order.order_id,
            event_type=outbox_event,
            payload={"order_id": order.order_id, "environment": env},
            salt=f"submit|{order.order_id}",
        )
        writer.persist_order(order, events=events, fills=[], outbox=ob)
        outbox_ids.append(ob.outbox_id)
        _ops_audit_order(
            ops_service,
            event_type="ORDER_SUBMIT",
            order=order,
            account_id=account_id,
            strategy_id=strategy_id,
        )

        if async_submit:
            # 仅 enqueue；由 drain_outbox 推送
            orders.append(order)
            all_events.extend(events)
            continue

        report = port.submit(order)
        order, more_events, fills = _apply_report_to_order(
            order,
            report,
            writer=writer,
            portfolio_service=portfolio_service,
            events=events,
        )
        writer.mark_outbox(ob.outbox_id, "SENT")
        position_events.extend([])  # bridge 已在 _apply 内写
        orders.append(order)
        all_fills.extend(fills)
        all_events.extend(events)
        for f in fills:
            _ops_audit_order(
                ops_service,
                event_type="EXECUTION_RECEIVED",
                order=order,
                account_id=account_id,
                strategy_id=strategy_id,
                reason=str(getattr(f, "fill_id", "") or "fill"),
            )

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
            "environment": env,
            **meta,
        },
    )


def run_cancel(
    order: Order,
    *,
    reason: str = "",
    writer: Any,
    broker_port: BrokerPort | None = None,
    paper_broker: Any = None,
    ops_service: Any = None,
) -> Order:
    port = broker_port or paper_broker
    cur, events, req = apply_cancel(order, reason=reason, paper_broker=port)
    writer.persist_cancel(cur, events=events, request=req)
    meta = dict(getattr(cur, "metadata", None) or {})
    _ops_audit_order(
        ops_service,
        event_type="ORDER_CANCEL",
        order=cur,
        account_id=str(getattr(cur, "account_id", "") or ""),
        strategy_id=str(meta.get("strategy_id") or ""),
        reason=reason,
    )
    return cur


def run_replace(
    order: Order,
    *,
    quantity: Optional[float] = None,
    limit_price: Optional[float] = None,
    writer: Any,
    broker_port: BrokerPort | None = None,
    paper_broker: Any = None,
) -> Order:
    port = broker_port or paper_broker
    cur, events, ver, req = apply_replace(
        order,
        quantity=quantity,
        limit_price=limit_price,
        paper_broker=port,
    )
    writer.persist_replace(cur, events=events, version=ver, request=req)
    return cur
