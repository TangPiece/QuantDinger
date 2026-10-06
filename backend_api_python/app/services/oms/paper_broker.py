"""Paper Broker：即时撮合；禁止交易所 HTTP / DataSourceFactory。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from .hash import compute_fill_id
from .protocol import ExecutionReport, Fill, Order


class PaperBroker:
    """PAPER only：accept / partial / fill / cancel / reject / latency stub。"""

    def __init__(
        self,
        *,
        prices: Mapping[str, float] | None = None,
        default_price: float = 10.0,
    ) -> None:
        self._prices = dict(prices or {})
        self._default_price = float(default_price)

    def set_prices(self, prices: Mapping[str, float]) -> None:
        self._prices.update(dict(prices))

    def _price_for(self, order: Order) -> float:
        key = order.instrument_key
        if key in self._prices and float(self._prices[key]) > 0:
            return float(self._prices[key])
        if order.limit_price is not None and float(order.limit_price) > 0:
            return float(order.limit_price)
        return self._default_price

    def submit(self, order: Order) -> ExecutionReport:
        """默认即时全成；metadata 可注入 partial/reject/timeout。"""
        meta = dict(order.metadata or {})
        inject = dict(meta.get("paper_broker") or meta)

        # latency_ms stub：仅记录，不 sleep
        latency_ms = float(inject.get("latency_ms") or 0)

        if inject.get("reject") or inject.get("broker_reject"):
            return ExecutionReport(
                report_id=f"rej_{order.order_id[:12]}",
                order_id=order.order_id,
                status="REJECT",
                message=str(inject.get("reject_reason") or "paper reject"),
                metadata={"latency_ms": latency_ms},
            )

        if inject.get("timeout_unknown") or inject.get("unknown"):
            return ExecutionReport(
                report_id=f"unk_{order.order_id[:12]}",
                order_id=order.order_id,
                status="UNKNOWN",
                message=str(inject.get("unknown_reason") or "paper timeout"),
                metadata={"latency_ms": latency_ms},
            )

        px = self._price_for(order)
        # LIMIT：买价不高于限价、卖价不低于限价才成交
        if str(order.order_type) == "LIMIT" and order.limit_price is not None:
            lim = float(order.limit_price)
            if str(order.side) == "BUY" and px > lim + 1e-12:
                return ExecutionReport(
                    report_id=f"ack_{order.order_id[:12]}",
                    order_id=order.order_id,
                    broker_order_id=f"paper_{order.order_id[:16]}",
                    status="ACK",
                    message="limit not marketable",
                    metadata={"latency_ms": latency_ms, "resting": True},
                )
            if str(order.side) == "SELL" and px < lim - 1e-12:
                return ExecutionReport(
                    report_id=f"ack_{order.order_id[:12]}",
                    order_id=order.order_id,
                    broker_order_id=f"paper_{order.order_id[:16]}",
                    status="ACK",
                    message="limit not marketable",
                    metadata={"latency_ms": latency_ms, "resting": True},
                )
            px = lim if str(order.side) == "BUY" else lim

        partials: Sequence[float] = inject.get("partial_fills") or []
        now = datetime.now(timezone.utc).isoformat()
        fills: list[Fill] = []
        remaining = float(order.quantity)

        if partials:
            for i, q in enumerate(partials):
                qq = min(float(q), remaining)
                if qq <= 0:
                    continue
                fills.append(
                    Fill(
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
                        metadata={"partial_index": i},
                    )
                )
                remaining -= qq
            status = "FILL" if remaining <= 1e-12 else "PARTIAL"
        else:
            # FOK：必须全成；IOC：可部分（默认全成）
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
                )
            )
            status = "FILL"
            remaining = 0.0

        filled = sum(f.quantity for f in fills)
        return ExecutionReport(
            report_id=f"er_{order.order_id[:12]}",
            order_id=order.order_id,
            broker_order_id=f"paper_{order.order_id[:16]}",
            status=status,
            filled_quantity=filled,
            last_quantity=fills[-1].quantity if fills else 0.0,
            last_price=px,
            avg_price=px,
            fills=fills,
            message="paper fill",
            metadata={"latency_ms": latency_ms, "remaining": remaining},
        )

    def cancel(self, order: Order, *, reason: str = "") -> ExecutionReport:
        return ExecutionReport(
            report_id=f"cx_{order.order_id[:12]}",
            order_id=order.order_id,
            broker_order_id=order.broker_order_id or f"paper_{order.order_id[:16]}",
            status="CANCEL",
            filled_quantity=float(order.filled_quantity),
            message=reason or "paper cancel",
        )

    def replace(
        self,
        order: Order,
        *,
        quantity: Optional[float] = None,
        limit_price: Optional[float] = None,
    ) -> ExecutionReport:
        """改单 ACK；不自动成交（由后续 submit/drain 处理）。"""
        return ExecutionReport(
            report_id=f"rp_{order.order_id[:12]}",
            order_id=order.order_id,
            broker_order_id=order.broker_order_id or f"paper_{order.order_id[:16]}",
            status="ACK",
            message="paper replace ack",
            metadata={
                "replaced_quantity": quantity,
                "replaced_limit_price": limit_price,
            },
        )
