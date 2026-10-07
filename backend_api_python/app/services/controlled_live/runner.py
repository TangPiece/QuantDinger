"""Phase 7C/7D：ControlledLiveService — 预算内多笔 LIMIT real submit。"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional
from uuid import uuid4

from app.services.live_readonly.gate import transition_environment
from app.services.oms.protocol import Order
from app.services.research_data.contracts import OrderIntent, TradingEnvironmentStateRecord
from app.services.research_data.registry import ResearchRegistry

from .adapter import query_by_client_order_id, submit_via_gateway
from .client_order_id import derive_client_order_id
from .compare import compare_shadow_vs_real
from .config import allow_real_submit, load_controlled_live_config
from .gate import ControlledLiveDenied, ControlledLiveGate, require_operator_approval
from .lineage import stamp_lineage
from .modes import normalize_environment
from .protocol import ControlledOrder, ControlledSession, OperatorApproval
from . import metrics as cl_metrics
from . import reconcile_loop
from .risk_budget import check_order_budget, record_order_submit
from .session import halt_session, merge_session_update, open_controlled_session
from .timeout import recover_unknown_order
from .writers import ControlledLiveWriter


class ControlledLiveError(RuntimeError):
    pass


class ControlledLiveService:
    """Gate → Gateway → 1x LIMIT；无 cancel/replace API。"""

    def __init__(
        self,
        store: Any,
        registry: ResearchRegistry,
        *,
        safety: Any | None = None,
        recon: Any | None = None,
        oms: Any | None = None,
        shadow: Any | None = None,
        ops: Any | None = None,
        broker_port: Any | None = None,
        writer: ControlledLiveWriter | None = None,
        gate: ControlledLiveGate | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._safety = safety
        self._recon = recon
        self._oms = oms
        self._shadow = shadow
        self._ops = ops
        self._broker = broker_port
        self._writer = writer or ControlledLiveWriter(registry)
        self._gate = gate or ControlledLiveGate(registry, safety=safety)
        self._session: ControlledSession | None = None
        self._environment = "LIVE_READONLY"
        self._approval: OperatorApproval | None = None
        self._orders: dict[str, ControlledOrder] = {}

    def set_environment(
        self,
        to_env: str,
        *,
        actor: str = "",
        approval_token: str = "",
        from_env: str | None = None,
    ) -> str:
        """阶梯进入 LIVE_CONTROLLED（需 PRODUCTION_READY + 审计 token hash）。"""
        src = from_env or self._environment
        dst = transition_environment(
            from_env=src,
            to_env=to_env,
            registry=self._registry,
            ops_service=self._ops,
            actor=actor or "operator",
        )
        if dst == "LIVE_CONTROLLED" and self._session and approval_token:
            self._approval = require_operator_approval(
                session=self._session,
                operator=actor or "operator",
                approval_token=approval_token,
            )
            self._writer.write_approval(self._approval)
        self._environment = dst
        self._registry.upsert_trading_environment_state(
            TradingEnvironmentStateRecord(
                account_id=self._session.account_id if self._session else "global",
                environment=dst,
                updated_at=datetime.now(timezone.utc).isoformat(),
                metadata={"actor": actor},
            )
        )
        return dst

    def start_session(
        self,
        *,
        account_id: str,
        approved_strategy_id: str,
        dataset_hash: str,
        model_version: str,
        strategy_version: str,
        feature_version: str = "",
        processor_version: str = "",
        snapshot_id: str = "",
        config: Any | None = None,
        effective_caps: Mapping[str, Any] | None = None,
    ) -> ControlledSession:
        cfg = config or load_controlled_live_config()
        session = open_controlled_session(
            account_id=account_id,
            approved_strategy_id=approved_strategy_id,
            dataset_hash=dataset_hash,
            model_version=model_version,
            strategy_version=strategy_version,
            feature_version=feature_version,
            processor_version=processor_version,
            snapshot_id=snapshot_id,
            config=cfg,
            effective_caps=effective_caps,
        )
        self._writer.write_session(session)
        self._session = session
        return session

    def approve(self, operator: str, *, scope: str = "SINGLE_ORDER", approval_token: str = "") -> OperatorApproval:
        if self._session is None:
            raise ControlledLiveError("no session")
        appr = require_operator_approval(
            session=self._session,
            operator=operator,
            approval_token=approval_token or f"token-{uuid4().hex[:8]}",
            scope=scope,
        )
        self._approval = appr
        self._writer.write_approval(appr)
        return appr

    def submit_single_intent(
        self,
        intent: OrderIntent,
        *,
        quote: Mapping[str, Any] | None = None,
        strategy_id: str = "",
    ) -> ControlledOrder:
        """Gate → 幂等 client_order_id → Gateway POST（至多一次）。"""
        if self._session is None:
            raise ControlledLiveError("no session")
        if self._session.status in ("SAFETY_HOLD", "HALTED", "CLOSED"):
            raise ControlledLiveDenied(
                f"session {self._session.status}: {self._session.stop_reason or 'halted'}"
            )
        if self._broker is None:
            raise ControlledLiveError("broker_port not configured")
        if normalize_environment(self._environment) != "LIVE_CONTROLLED":
            raise ControlledLiveDenied("submit only in LIVE_CONTROLLED")

        if strategy_id and self._session.approved_strategy_id != strategy_id:
            raise ControlledLiveDenied("approved_strategy_id mismatch")

        notional = float(intent.quantity or 0) * float(intent.limit_price or 0)
        ok, budget_reason = check_order_budget(self._session, notional=notional)
        if not ok:
            cl_metrics.record_risk_breach(
                self._ops, account_id=self._session.account_id, reason=budget_reason
            )
            raise ControlledLiveDenied(f"risk budget: {budget_reason}")

        if self._safety is not None:
            try:
                sd = self._safety.decide(
                    self._session.account_id,
                    intent=intent,
                    strategy_id=strategy_id or self._session.approved_strategy_id,
                )
                if str(sd.decision).upper() != "ALLOW":
                    raise ControlledLiveDenied(sd.reason or "safety blocked")
            except ControlledLiveDenied:
                raise
            except Exception:
                raise ControlledLiveDenied("safety fail-closed")

        self._gate.assert_allow(
            environment=self._environment,
            session=self._session,
            intent=intent,
            quote=quote,
            approval=self._approval,
            notional_override=notional,
        )

        seq = max(1, int(self._session.order_count) + 1)
        cid = derive_client_order_id(session_id=self._session.session_id, seq=seq)
        existing = self._orders.get(cid)
        if existing:
            return existing

        # 提交前先 query：已存在则采用，不 POST
        try:
            raw_existing = query_by_client_order_id(self._broker, cid)
            if raw_existing.get("id") or str(raw_existing.get("status", "")).lower() not in (
                "",
                "unknown",
            ):
                order = _order_from_broker(
                    session=self._session,
                    intent=intent,
                    client_order_id=cid,
                    raw=raw_existing,
                    lineage=stamp_lineage(session=self._session, intent=intent, strategy_id=strategy_id),
                )
                self._persist_order(order)
                return order
        except Exception:
            pass

        oms_order = Order(
            order_id="clord_" + uuid4().hex[:16],
            client_order_id=cid,
            account_id=self._session.account_id,
            instrument_key=intent.instrument_key,
            side=intent.side,
            order_type="LIMIT",
            quantity=float(intent.quantity),
            limit_price=float(intent.limit_price or 0),
            metadata={"symbol": _symbol(intent)},
        )
        lineage = stamp_lineage(session=self._session, intent=intent, strategy_id=strategy_id)
        t0 = time.monotonic()
        try:
            raw = submit_via_gateway(
                environment=self._environment,
                order=oms_order,
                broker_port=self._broker,
            )
            latency_ms = (time.monotonic() - t0) * 1000.0
            order = _order_from_broker(
                session=self._session,
                intent=intent,
                client_order_id=cid,
                raw=raw if isinstance(raw, dict) else {},
                lineage=lineage,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            # NETWORK → UNKNOWN，仅允许后续 query recover
            order = ControlledOrder(
                order_id=oms_order.order_id,
                session_id=self._session.session_id,
                client_order_id=cid,
                symbol=_symbol(intent),
                side=intent.side,
                quantity=float(intent.quantity),
                limit_price=float(intent.limit_price),
                status="UNKNOWN",
                lineage=lineage,
                created_at=datetime.now(timezone.utc).isoformat(),
                metadata={"submit_error": str(exc)[:200]},
            )
            self._persist_order(order)
            self._session = record_order_submit(self._session, notional=notional, rejected=False)
            self._engage_safety_hold("submit_unknown")
            cl_metrics.record_order_submitted(self._ops, account_id=self._session.account_id)
            return order

        self._persist_order(order)
        rejected = str(order.status).upper() == "REJECTED"
        self._session = record_order_submit(
            self._session, notional=notional, rejected=rejected
        )
        self._writer.write_session(self._session)
        cl_metrics.record_order_submitted(self._ops, account_id=self._session.account_id)
        cl_metrics.record_order_terminal(
            self._ops, account_id=self._session.account_id, status=order.status
        )
        # 7D：FILLED 不默认 kill session；UNKNOWN/REJECTED/预算用尽才 SAFETY_HOLD
        if order.status == "UNKNOWN":
            self._engage_safety_hold("submit_unknown")
        elif order.status == "REJECTED":
            self._engage_safety_hold("terminal_REJECTED")
        elif self._session.order_count >= self._session.config.max_orders:
            self._engage_safety_hold("session_budget_exhausted")
        return order

    def recover_unknown(self, client_order_id: str) -> ControlledOrder:
        """Timeout/UNKNOWN：只 query，禁止 resubmit。"""
        if self._broker is None:
            raise ControlledLiveError("broker_port not configured")
        order = self._orders.get(client_order_id)
        if order is None:
            raise ControlledLiveError("unknown client_order_id")
        recovered = recover_unknown_order(order=order, query_port=self._broker)
        self._persist_order(recovered, increment_count=False)
        return recovered

    def compare_shadow_vs_real(self, order_id: str) -> Any:
        order = next((o for o in self._orders.values() if o.order_id == order_id), None)
        if order is None:
            raise ControlledLiveError("order not found")
        shadow_fill: dict[str, Any] = {}
        if self._shadow is not None:
            try:
                for so in getattr(self._shadow._oms, "list_orders", lambda: [])():
                    if so.symbol.upper() == order.symbol.upper():
                        shadow_fill = {
                            "symbol": so.symbol,
                            "filled_quantity": so.filled_quantity,
                            "avg_fill_price": so.limit_price or 0,
                        }
                        break
            except Exception:
                pass
        real_fill = {
            "symbol": order.symbol,
            "filled_quantity": order.filled_quantity,
            "avg_fill_price": order.avg_fill_price,
        }
        latency = float(order.metadata.get("latency_ms") or 0)
        report = compare_shadow_vs_real(
            order_id=order_id,
            account_id=self._session.account_id if self._session else "",
            shadow_fill=shadow_fill,
            real_fill=real_fill,
            submit_latency_ms=latency,
        )
        self._writer.write_compare_run(report)
        return report

    def reconcile(self, account_id: str, portfolio_id: str = "") -> dict[str, Any]:
        """Hook 6F：FAST 对账；CRITICAL → Safety + Session halt。"""
        if self._session is None:
            return {"status": "SKIPPED", "reason": "no_session"}
        sess, result = reconcile_loop.after_submit_or_tick(
            self._recon,
            self._safety,
            self._session,
            portfolio_id=portfolio_id or account_id,
            ops=self._ops,
        )
        self._session = sess
        self._writer.write_session(sess)
        return {"account_id": account_id, **result}

    def _persist_order(self, order: ControlledOrder, *, increment_count: bool = True) -> None:
        self._orders[order.client_order_id] = order
        if self._session and increment_count and order.status not in ("PENDING_SUBMIT",):
            sess = merge_session_update(
                self._session,
                {"order_count": self._session.order_count + 1},
            )
            self._session = sess
            self._writer.write_session(sess)
        self._writer.write_order_index(order, session_id=self._session.session_id if self._session else "")

    def _engage_safety_hold(self, reason: str) -> None:
        if self._session:
            self._session = halt_session(self._session, stop_reason=reason)
            self._writer.write_session(self._session)
        if self._safety is not None:
            try:
                self._safety.engage_kill_switch(
                    scope="ACCOUNT",
                    scope_id=self._session.account_id if self._session else "global",
                    reason=reason,
                    operator="controlled_live",
                )
            except Exception:
                pass
        self._emit_ops_denial(reason)

    def _emit_ops_denial(self, reason: str) -> None:
        if self._ops is None:
            return
        try:
            self._ops.emit_audit(
                event_type="CONTROLLED_LIVE_DENIED",
                account_id=self._session.account_id if self._session else "",
                reason=reason,
                metadata={"environment": self._environment},
            )
        except Exception:
            pass


def _symbol(intent: OrderIntent) -> str:
    key = str(intent.instrument_key or "")
    return key.split(":", 1)[1].upper() if ":" in key else key.upper()


def _order_from_broker(
    *,
    session: ControlledSession,
    intent: OrderIntent,
    client_order_id: str,
    raw: dict[str, Any],
    lineage: dict[str, Any],
    latency_ms: float = 0.0,
) -> ControlledOrder:
    st = str(raw.get("status") or "SUBMITTED").upper()
    mapping = {
        "NEW": "ACCEPTED",
        "ACCEPTED": "ACCEPTED",
        "PARTIALLY_FILLED": "PARTIALLY_FILLED",
        "FILLED": "FILLED",
        "REJECTED": "REJECTED",
        "EXPIRED": "EXPIRED",
    }
    status = mapping.get(st, "SUBMITTED")
    return ControlledOrder(
        order_id="clord_" + uuid4().hex[:16],
        session_id=session.session_id,
        client_order_id=client_order_id,
        broker_order_id=str(raw.get("id") or ""),
        symbol=_symbol(intent),
        side=intent.side,
        quantity=float(intent.quantity),
        limit_price=float(intent.limit_price or 0),
        status=status,  # type: ignore[arg-type]
        filled_quantity=float(raw.get("filled_qty") or 0),
        avg_fill_price=float(raw.get("filled_avg_price") or 0),
        lineage=lineage,
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={"latency_ms": latency_ms, "allow_real_submit": allow_real_submit()},
    )


def default_broker_for_env() -> Any:
    """CI 默认 Fake；真实 adapter 需 opt-in。"""
    from app.services.broker_adapter.adapters.alpaca.controlled_live_adapter import (
        AlpacaControlledLiveAdapter,
        FakeControlledLiveAdapter,
    )

    if allow_real_submit():
        return AlpacaControlledLiveAdapter()
    return FakeControlledLiveAdapter()
