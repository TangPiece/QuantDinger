"""connect → command → normalize → persist raw/index。"""

from __future__ import annotations

from typing import Any, Callable, Optional

from app.services.oms.protocol import ExecutionReport, Order

from .dedup import ExecutionDeduper
from .errors import AdapterErrorCode, BrokerAdapterError, redact_secrets
from .protocol import BrokerAdapter
from .writers import BrokerWriter


def submit_via_adapter(
    adapter: BrokerAdapter,
    order: Order,
    *,
    writer: BrokerWriter | None = None,
    deduper: ExecutionDeduper | None = None,
) -> ExecutionReport:
    """提交并可选写 link / raw / dedup。"""
    try:
        report = adapter.submit_order(order)
    except BrokerAdapterError as exc:
        if exc.code == AdapterErrorCode.NETWORK_UNKNOWN:
            return ExecutionReport(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="UNKNOWN",
                message=redact_secrets(str(exc)),
            )
        raise
    except Exception as exc:  # 网络类 → UNKNOWN，禁止自动重下
        return ExecutionReport(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            status="UNKNOWN",
            message=redact_secrets(f"NETWORK_UNKNOWN: {exc}"),
        )

    if writer is not None:
        writer.link_order(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            broker_order_id=report.broker_order_id or "",
            broker_id=getattr(adapter, "broker_id", ""),
            account_id=order.account_id,
        )
        if report.broker_event_id or report.report_id:
            eid = report.broker_event_id or report.report_id
            if deduper is None or deduper.try_accept(
                getattr(adapter, "broker_id", ""), eid
            ):
                writer.persist_raw_event(
                    broker_id=getattr(adapter, "broker_id", ""),
                    event_id=eid,
                    payload=report.model_dump(mode="json"),
                )
                if writer is not None and eid:
                    writer.try_dedup(getattr(adapter, "broker_id", ""), eid)
    return report


def pump_adapter_events(
    adapter: Any,
    callback: Callable[[ExecutionReport], None],
    *,
    writer: BrokerWriter | None = None,
    deduper: ExecutionDeduper | None = None,
) -> int:
    """WS 事件泵：dedup + raw + callback。"""
    if not hasattr(adapter, "pump_events"):
        return 0

    def _cb(report: ExecutionReport) -> None:
        if writer is not None and (report.broker_event_id or report.report_id):
            eid = report.broker_event_id or report.report_id
            bid = getattr(adapter, "broker_id", "")
            if deduper is None or deduper.try_accept(bid, eid):
                writer.persist_raw_event(
                    broker_id=bid,
                    event_id=eid,
                    payload=report.model_dump(mode="json"),
                )
                writer.try_dedup(bid, eid)
                callback(report)
            # 重复事件丢弃
            return
        callback(report)

    return int(adapter.pump_events(_cb))
