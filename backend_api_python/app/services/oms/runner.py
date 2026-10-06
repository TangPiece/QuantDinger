"""OMSService：submit_intents / cancel / replace / drain_outbox / recover_unknown。"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from app.services.research_data.contracts import OmsOutboxRecord, OrderIntent
from app.services.research_data.registry import ResearchRegistry

from .artifact_store import OmsArtifactStore
from .broker_port import BrokerPort
from .cycle import run_cancel, run_replace, run_submit_intents
from .events import append_event
from .fill_bridge import bridge_fills_to_portfolio
from .outbox import OutboxService
from .paper_broker import PaperBroker
from .protocol import ENGINE_VERSION, Order, OutboxRecord, SubmitResult
from .reducer import apply_execution_report
from .state_machine import StateMachineError
from .writers import OmsWriter


class OMSError(RuntimeError):
    """OMS 编排错误。"""


class OMSService:
    """Order Lifecycle；6E 支持 PAPER|SANDBOX|SHADOW（经 BrokerPort）。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        portfolio_service: Any = None,
        paper_broker: PaperBroker | None = None,
        broker_port: BrokerPort | None = None,
        artifact_store: OmsArtifactStore | None = None,
        broker_adapter_service: Any = None,
        trading_gate: Any = None,
        ops_service: Any = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._portfolio = portfolio_service
        self._trading_gate = trading_gate
        self._ops = ops_service
        # 默认 PaperBroker；可由 6E PaperBrokerAdapter / Simulated 注入
        if broker_port is not None:
            self._port: BrokerPort = broker_port
        elif paper_broker is not None:
            self._port = paper_broker  # type: ignore[assignment]
        else:
            self._port = PaperBroker()  # type: ignore[assignment]
        self._paper = self._port  # 兼容旧字段名
        self._broker_svc = broker_adapter_service
        self._writer = OmsWriter(registry, artifact_store=artifact_store)

        def _enqueue(rec: OutboxRecord) -> None:
            self._registry.enqueue_outbox(
                OmsOutboxRecord(
                    outbox_id=rec.outbox_id,
                    aggregate_type=rec.aggregate_type,
                    aggregate_id=rec.aggregate_id,
                    event_type=rec.event_type,
                    status=str(rec.status),
                    payload_json=dict(rec.payload_json or {}),
                    created_at=rec.created_at,
                    sent_at=rec.sent_at,
                )
            )

        self._outbox = OutboxService(
            enqueue_fn=_enqueue,
            list_fn=lambda limit: self._writer.list_outbox(limit=limit),
            mark_fn=lambda oid, st: self._writer.mark_outbox(oid, st),
        )

    def set_trading_gate(self, gate: Any) -> None:
        """6F：注入 TradingGate（阻断新 submit）。"""
        self._trading_gate = gate

    def set_ops_service(self, ops_service: Any) -> None:
        """6H：Monitoring / Audit 钩子。"""
        self._ops = ops_service

    def submit_intents(
        self,
        intents: Sequence[OrderIntent] | list[OrderIntent],
        *,
        account_id: str,
        portfolio_id: str,
        risk_run_id: str = "",
        policy_hash: str = "",
        environment: str = "PAPER",
        metadata: dict[str, Any] | None = None,
        prices: Mapping[str, float] | None = None,
    ) -> SubmitResult:
        meta = dict(metadata or {})
        if prices is None and "prices" in meta:
            prices = dict(meta.get("prices") or {})
        try:
            return run_submit_intents(
                list(intents),
                account_id=account_id,
                portfolio_id=portfolio_id,
                risk_run_id=risk_run_id,
                policy_hash=policy_hash,
                environment=environment,
                writer=self._writer,
                broker_port=self._port,
                portfolio_service=self._portfolio,
                prices=prices,
                metadata=meta,
                trading_gate=self._trading_gate,
                ops_service=self._ops,
            )
        except StateMachineError as exc:
            raise OMSError(str(exc)) from exc
        except Exception as exc:
            # ValidationError / TradingGateBlocked → OMSError
            from .validation import ValidationError

            if isinstance(exc, ValidationError):
                raise OMSError(str(exc)) from exc
            raise

    def cancel(self, order_id: str, *, reason: str = "") -> Order:
        order = self.get_order(order_id)
        try:
            return run_cancel(
                order,
                reason=reason,
                writer=self._writer,
                broker_port=self._port,
                ops_service=self._ops,
            )
        except StateMachineError as exc:
            raise OMSError(str(exc)) from exc

    def replace(
        self,
        order_id: str,
        *,
        quantity: Optional[float] = None,
        limit_price: Optional[float] = None,
    ) -> Order:
        order = self.get_order(order_id)
        try:
            return run_replace(
                order,
                quantity=quantity,
                limit_price=limit_price,
                writer=self._writer,
                broker_port=self._port,
            )
        except Exception as exc:
            raise OMSError(str(exc)) from exc

    def get_order(self, order_id: str) -> Order:
        return self._writer.get_order(order_id)

    def list_orders(self, *, account_id: str = "", status: str = "") -> list[Order]:
        return self._writer.list_orders(account_id=account_id, status=status)

    def list_fills(self, order_id: str):
        return self._writer.list_fills(order_id)

    def list_events(self, order_id: str):
        return self._writer.list_events(order_id)

    def recover_unknown_order(self, order_id: str) -> Order:
        """UNKNOWN → query BrokerPort / Adapter → apply_execution_report；禁止重下单。"""
        order = self.get_order(order_id)
        if str(order.status) != "UNKNOWN":
            return order
        report = None
        if self._broker_svc is not None:
            report = self._broker_svc.recover_order(order)
        elif hasattr(self._port, "recover_unknown"):
            report = self._port.recover_unknown(order)  # type: ignore[attr-defined]
        else:
            raise OMSError("no recover path on broker_port")
        events = []
        # UNKNOWN → ACK/FILL/... 合法
        order, more, fills = apply_execution_report(order, report)
        events.extend(more)
        self._writer.persist_order(order, events=events, fills=fills)
        if fills:
            bridge_fills_to_portfolio(
                order, fills, portfolio_service=self._portfolio
            )
        return order

    def drain_outbox(self, *, limit: int = 100) -> int:
        """推送 PENDING outbox（PAPER_SUBMIT | BROKER_SUBMIT）。"""

        def _handler(rec: OutboxRecord) -> None:
            if rec.event_type not in ("PAPER_SUBMIT", "BROKER_SUBMIT"):
                return
            oid = rec.aggregate_id or str(
                (rec.payload_json or {}).get("order_id") or ""
            )
            if not oid:
                return
            try:
                order = self.get_order(oid)
            except KeyError:
                return
            if str(order.status) not in ("SUBMITTED",):
                return
            report = self._port.submit(order)
            events = []
            if str(report.status).upper() in (
                "FILL",
                "PARTIAL",
                "FILLED",
                "PARTIALLY_FILLED",
            ):
                order, ev = append_event(
                    order,
                    event_type="ACKNOWLEDGED",
                    new_status="ACKNOWLEDGED",
                    source="BROKER",
                    message="drain ack",
                )
                events.append(ev)
            order, more, fills = apply_execution_report(order, report)
            events.extend(more)
            self._writer.persist_order(order, events=events, fills=fills)
            bridge_fills_to_portfolio(
                order, fills, portfolio_service=self._portfolio
            )

        return self._outbox.drain(_handler, limit=limit)


__all__ = ["ENGINE_VERSION", "OMSError", "OMSService"]
