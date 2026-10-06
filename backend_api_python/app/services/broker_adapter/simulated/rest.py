"""Fake REST：内存订单簿 + command API。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from uuid import uuid4

from app.services.oms.hash import compute_fill_id
from app.services.oms.protocol import ExecutionReport, Fill, Order

from ..events import make_normalized_event
from ..execution_bridge import event_to_execution_report
from ..mapping import map_broker_status
from ..state_machine import assert_sim_transition


class SimulatedRestBook:
    """进程内模拟券商 REST。"""

    def __init__(
        self,
        *,
        prices: Mapping[str, float] | None = None,
        default_price: float = 10.0,
        broker_id: str = "simulated",
    ) -> None:
        self.broker_id = broker_id
        self._prices = dict(prices or {})
        self._default_price = float(default_price)
        # client_order_id → book row
        self._orders: dict[str, dict[str, Any]] = {}
        self._executions: list[dict[str, Any]] = []
        self._event_seq = 0

    def set_prices(self, prices: Mapping[str, float]) -> None:
        self._prices.update(dict(prices))

    def _price(self, order: Order) -> float:
        key = order.instrument_key
        if key in self._prices and float(self._prices[key]) > 0:
            return float(self._prices[key])
        if order.limit_price is not None and float(order.limit_price) > 0:
            return float(order.limit_price)
        return self._default_price

    def _next_exec_id(self) -> str:
        self._event_seq += 1
        return f"sim_exec_{self._event_seq:06d}"

    def submit(self, order: Order) -> ExecutionReport:
        meta = dict(order.metadata or {})
        inject = dict(meta.get("paper_broker") or meta.get("simulated") or meta)

        if inject.get("reject") or inject.get("broker_reject"):
            return ExecutionReport(
                report_id=f"rej_{order.order_id[:12]}",
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="REJECT",
                message=str(inject.get("reject_reason") or "sim reject"),
            )

        if inject.get("timeout_unknown") or inject.get("unknown"):
            # 订单实际可能已进簿，但回报 UNKNOWN（禁止自动重下）
            broker_oid = f"sim_{order.order_id[:16]}"
            self._orders[order.client_order_id] = {
                "order": order,
                "broker_order_id": broker_oid,
                "status": "NEW",
                "filled": 0.0,
                "avg_price": 0.0,
                "hidden_success": True,
            }
            return ExecutionReport(
                report_id=f"unk_{order.order_id[:12]}",
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                broker_order_id=broker_oid,
                status="UNKNOWN",
                message=str(inject.get("unknown_reason") or "sim timeout"),
            )

        broker_oid = f"sim_{order.order_id[:16]}"
        px = self._price(order)

        # LIMIT 不可成交 → resting ACK
        if str(order.order_type) == "LIMIT" and order.limit_price is not None:
            lim = float(order.limit_price)
            if str(order.side) == "BUY" and px > lim + 1e-12:
                self._orders[order.client_order_id] = {
                    "order": order,
                    "broker_order_id": broker_oid,
                    "status": "NEW",
                    "filled": 0.0,
                    "avg_price": 0.0,
                }
                return ExecutionReport(
                    report_id=f"ack_{order.order_id[:12]}",
                    order_id=order.order_id,
                    client_order_id=order.client_order_id,
                    broker_order_id=broker_oid,
                    status="ACK",
                    message="limit not marketable",
                    metadata={"resting": True},
                )
            if str(order.side) == "SELL" and px < lim - 1e-12:
                self._orders[order.client_order_id] = {
                    "order": order,
                    "broker_order_id": broker_oid,
                    "status": "NEW",
                    "filled": 0.0,
                    "avg_price": 0.0,
                }
                return ExecutionReport(
                    report_id=f"ack_{order.order_id[:12]}",
                    order_id=order.order_id,
                    client_order_id=order.client_order_id,
                    broker_order_id=broker_oid,
                    status="ACK",
                    message="limit not marketable",
                    metadata={"resting": True},
                )
            px = lim

        partials = inject.get("partial_fills") or []
        fills: list[Fill] = []
        remaining = float(order.quantity)
        now = datetime.now(timezone.utc).isoformat()

        if partials:
            for i, q in enumerate(partials):
                qq = min(float(q), remaining)
                if qq <= 0:
                    continue
                exec_id = self._next_exec_id()
                fill = Fill(
                    fill_id=compute_fill_id(
                        order.order_id, quantity=qq, price=px, salt=f"p|{i}"
                    ),
                    order_id=order.order_id,
                    instrument_key=order.instrument_key,
                    side=order.side,
                    quantity=qq,
                    price=px,
                    trading_date=order.trading_date,
                    created_at=now,
                    metadata={"broker_execution_id": exec_id},
                )
                fills.append(fill)
                self._executions.append(
                    {
                        "broker_execution_id": exec_id,
                        "client_order_id": order.client_order_id,
                        "quantity": qq,
                        "price": px,
                    }
                )
                remaining -= qq
            status = "FILL" if remaining <= 1e-12 else "PARTIAL"
            sim_status = "FILLED" if remaining <= 1e-12 else "PARTIALLY_FILLED"
        else:
            exec_id = self._next_exec_id()
            qty = float(order.quantity)
            fills.append(
                Fill(
                    fill_id=compute_fill_id(
                        order.order_id, quantity=qty, price=px, salt="full"
                    ),
                    order_id=order.order_id,
                    instrument_key=order.instrument_key,
                    side=order.side,
                    quantity=qty,
                    price=px,
                    trading_date=order.trading_date,
                    created_at=now,
                    metadata={"broker_execution_id": exec_id},
                )
            )
            self._executions.append(
                {
                    "broker_execution_id": exec_id,
                    "client_order_id": order.client_order_id,
                    "quantity": qty,
                    "price": px,
                }
            )
            status = "FILL"
            sim_status = "FILLED"
            remaining = 0.0

        filled = sum(f.quantity for f in fills)
        self._orders[order.client_order_id] = {
            "order": order,
            "broker_order_id": broker_oid,
            "status": sim_status,
            "filled": filled,
            "avg_price": px,
        }
        return ExecutionReport(
            report_id=f"er_{order.order_id[:12]}",
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            broker_order_id=broker_oid,
            status=status,
            filled_quantity=filled,
            last_quantity=fills[-1].quantity if fills else 0.0,
            last_price=px,
            avg_price=px,
            remaining_quantity=remaining,
            fills=fills,
            message="sim fill",
            broker_event_id=fills[-1].metadata.get("broker_execution_id", "")
            if fills
            else "",
        )

    def cancel(self, order: Order, *, reason: str = "") -> ExecutionReport:
        row = self._orders.get(order.client_order_id)
        if row is not None:
            assert_sim_transition(row["status"], "CANCELED")
            row["status"] = "CANCELED"
        return ExecutionReport(
            report_id=f"cx_{order.order_id[:12]}",
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            broker_order_id=(row or {}).get("broker_order_id")
            or order.broker_order_id
            or f"sim_{order.order_id[:16]}",
            status="CANCEL",
            filled_quantity=float((row or {}).get("filled") or order.filled_quantity),
            message=reason or "sim cancel",
        )

    def replace(
        self,
        order: Order,
        *,
        quantity: Optional[float] = None,
        limit_price: Optional[float] = None,
    ) -> ExecutionReport:
        row = self._orders.get(order.client_order_id)
        if row is not None:
            o = row["order"]
            updates: dict[str, Any] = {}
            if quantity is not None:
                updates["quantity"] = float(quantity)
            if limit_price is not None:
                updates["limit_price"] = float(limit_price)
                updates["order_type"] = "LIMIT"
            row["order"] = o.model_copy(update=updates)
            row["status"] = "NEW"
        return ExecutionReport(
            report_id=f"rp_{order.order_id[:12]}",
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            broker_order_id=(row or {}).get("broker_order_id")
            or order.broker_order_id
            or f"sim_{order.order_id[:16]}",
            status="ACK",
            message="sim replace ack",
            metadata={
                "replaced_quantity": quantity,
                "replaced_limit_price": limit_price,
            },
        )

    def get_order(self, client_order_id: str) -> dict[str, Any]:
        row = self._orders.get(client_order_id)
        if not row:
            raise KeyError(client_order_id)
        return row

    def list_open(self) -> list[dict[str, Any]]:
        return [
            r
            for r in self._orders.values()
            if r["status"] in ("NEW", "PARTIALLY_FILLED")
        ]

    def recent_executions(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._executions[-limit:])

    def recover_report(self, order: Order) -> ExecutionReport:
        """UNKNOWN 后 query：若 hidden_success 则返回真实状态。"""
        row = self._orders.get(order.client_order_id)
        if not row:
            return ExecutionReport(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="UNKNOWN",
                message="not found on broker",
            )
        sim_st = str(row["status"])
        oms_st = map_broker_status(sim_st)
        filled = float(row.get("filled") or 0)
        px = float(row.get("avg_price") or 0)
        fills: list[Fill] = []
        if filled > 0 and px > 0 and oms_st in ("FILL", "PARTIAL"):
            fills.append(
                Fill(
                    fill_id=compute_fill_id(
                        order.order_id, quantity=filled, price=px, salt="recover"
                    ),
                    order_id=order.order_id,
                    instrument_key=order.instrument_key,
                    side=order.side,
                    quantity=filled,
                    price=px,
                    trading_date=order.trading_date,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        return ExecutionReport(
            report_id=f"rec_{order.order_id[:12]}",
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            broker_order_id=str(row.get("broker_order_id") or ""),
            status=oms_st,
            filled_quantity=filled,
            avg_price=px,
            last_quantity=filled,
            last_price=px,
            remaining_quantity=max(0.0, float(order.quantity) - filled),
            fills=fills,
            message="recovered via get_order",
        )
