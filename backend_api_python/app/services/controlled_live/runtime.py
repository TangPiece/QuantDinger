"""Phase 7D：LiveTradingRuntime — tick 编排（粘合 production intents + ControlledLive）。"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from app.services.research_data.contracts import OrderIntent

from . import metrics as cl_metrics
from . import reconcile_loop
from . import stop_conditions
from .operator_status import OperatorStatusSnapshot, build_operator_status
from pydantic import Field

from app.services.research_data.contracts import _ContractModel

from .protocol import ControlledSession, RuntimePhase
from .risk_budget import check_order_budget
from .session import halt_session, merge_session_update, open_controlled_session


class RuntimeTickResult(_ContractModel):
    """单次 tick 摘要。"""

    tick_id: str
    session_id: str = ""
    intents_seen: int = 0
    orders_submitted: int = 0
    halted: bool = False
    stop_reason: str = ""
    runtime_phase: RuntimePhase = "POST_TICK"
    metadata: dict[str, Any] = Field(default_factory=dict)


IntentProvider = Callable[
    [ControlledSession, datetime], Sequence[OrderIntent] | list[OrderIntent]
]


class LiveTradingRuntime:
    """LIVE_CONTROLLED 可持续运行；不发 MARKET、不 auto flatten。"""

    def __init__(
        self,
        store: Any,
        registry: Any,
        *,
        md: Any | None = None,
        bridge: Any | None = None,
        risk: Any | None = None,
        controlled: Any | None = None,
        safety: Any | None = None,
        recon: Any | None = None,
        ops: Any | None = None,
        shadow: Any | None = None,
        production_runtime: Any | None = None,
        runtime_id: str = "",
        intent_provider: IntentProvider | None = None,
        writer: Any | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._md = md
        self._bridge = bridge
        self._risk = risk
        self._controlled = controlled
        self._safety = safety
        self._recon = recon
        self._ops = ops
        self._shadow = shadow
        self._production = production_runtime
        self._runtime_id = runtime_id
        self._intent_provider = intent_provider
        self._writer = writer
        self._session: ControlledSession | None = None
        self._last_tick_at: str = ""
        self._daily_pnl: float = 0.0

    @property
    def session(self) -> ControlledSession | None:
        return self._session

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
        **kwargs: Any,
    ) -> ControlledSession:
        """打开并锁定 TradingSession；ControlledLiveService 若存在则同步。"""
        sess = open_controlled_session(
            account_id=account_id,
            approved_strategy_id=approved_strategy_id,
            dataset_hash=dataset_hash,
            model_version=model_version,
            strategy_version=strategy_version,
            feature_version=feature_version,
            processor_version=processor_version,
            snapshot_id=snapshot_id,
            **kwargs,
        )
        self._session = sess
        if self._controlled is not None:
            try:
                self._controlled.start_session(
                    account_id=account_id,
                    approved_strategy_id=approved_strategy_id,
                    dataset_hash=dataset_hash,
                    model_version=model_version,
                    strategy_version=strategy_version,
                )
                self._controlled._session = merge_session_update(
                    self._controlled._session,
                    {
                        "feature_version": feature_version,
                        "processor_version": processor_version,
                        "snapshot_id": snapshot_id,
                        "risk_budget": sess.risk_budget,
                    },
                )
            except Exception:
                pass
        if self._writer is not None:
            try:
                self._writer.write_session(sess)
            except Exception:
                pass
        return sess

    def stop_session(self, *, reason: str = "operator_stop") -> ControlledSession | None:
        """CLOSED + stop_reason；不撤单。"""
        if self._session is None:
            return None
        self._session = merge_session_update(
            self._session,
            {"status": "CLOSED", "stop_reason": reason, "runtime_phase": "CLOSED"},
        )
        if self._writer is not None:
            try:
                self._writer.write_session(self._session)
            except Exception:
                pass
        return self._session

    def recover(self) -> ControlledSession | None:
        """Crash recovery：reload session + UNKNOWN 仅 query。"""
        if self._controlled is None or self._session is None:
            return self._session
        for order in list(getattr(self._controlled, "_orders", {}).values()):
            if str(order.status).upper() == "UNKNOWN":
                try:
                    self._controlled.recover_unknown(order.client_order_id)
                except Exception:
                    pass
        return self._session

    def status(self) -> OperatorStatusSnapshot:
        """Operator 聚合视图。"""
        safety_state = "NORMAL"
        if self._safety is not None and self._session is not None:
            try:
                st = self._safety._get_or_create_state(
                    "ACCOUNT", self._session.account_id
                )
                safety_state = str(st.state or "NORMAL")
            except Exception:
                safety_state = "UNKNOWN"
        orders = list(getattr(self._controlled, "_orders", {}).values()) if self._controlled else []
        return build_operator_status(
            session=self._session,
            orders=orders,
            safety_state=safety_state,
            daily_pnl=self._daily_pnl,
            last_tick_at=self._last_tick_at,
        )

    def tick(
        self,
        *,
        as_of: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeTickResult:
        """MD→infer→risk→budgeted submits→recon→post stop。"""
        t0 = time.monotonic()
        now = as_of or datetime.now(timezone.utc)
        tick_id = "cltick_" + uuid4().hex[:16]
        meta = dict(metadata or {})
        if self._session is None:
            return RuntimeTickResult(
                tick_id=tick_id,
                halted=True,
                stop_reason="no_session",
            )

        sess = self._session
        safety_state = meta.get("safety_state", "NORMAL")
        pre = stop_conditions.pre_tick(
            sess, md=self._md, broker=getattr(self._controlled, "_broker", None), safety_state=str(safety_state)
        )
        if pre.halt:
            sess = stop_conditions.apply_halt_to_session(sess, pre)
            self._session = sess
            if pre.stop_reason == "md_stale":
                cl_metrics.record_md_stale(self._ops, account_id=sess.account_id)
            return RuntimeTickResult(
                tick_id=tick_id,
                session_id=sess.session_id,
                halted=True,
                stop_reason=pre.stop_reason,
                runtime_phase="HALTED",
            )

        sess = merge_session_update(sess, {"runtime_phase": "INFER"})
        intents = self._collect_intents(sess, now, meta)
        sess = merge_session_update(sess, {"runtime_phase": "SUBMIT"})
        submitted = 0
        strategy_id = sess.approved_strategy_id

        for intent in intents:
            if sess.status in ("SAFETY_HOLD", "HALTED", "CLOSED"):
                break
            ok, reason = check_order_budget(
                sess, notional=float(intent.quantity or 0) * float(intent.limit_price or 0)
            )
            if not ok:
                cl_metrics.record_risk_breach(self._ops, account_id=sess.account_id, reason=reason)
                sess = halt_session(sess, stop_reason=reason)
                break
            if self._controlled is None:
                break
            try:
                self._controlled.submit_single_intent(
                    intent,
                    strategy_id=strategy_id,
                    quote=meta.get("quote"),
                )
                submitted += 1
                cl_metrics.record_order_submitted(self._ops, account_id=sess.account_id)
                sess = self._controlled._session or sess
            except Exception as exc:
                from .risk_budget import record_runtime_error

                sess = record_runtime_error(sess)
                meta["last_submit_error"] = str(exc)[:200]
                break

        sess = merge_session_update(sess, {"runtime_phase": "RECON"})
        if self._controlled is not None:
            self._controlled._session = sess
        sess, _recon = reconcile_loop.after_submit_or_tick(
            self._recon,
            self._safety,
            sess,
            inject=meta.get("recon_inject"),
            ops=self._ops,
        )
        recon_critical = reconcile_loop.critical_from_result(_recon)

        daily_pnl = float(meta.get("daily_pnl", self._daily_pnl))
        self._daily_pnl = daily_pnl
        unknown_n = sum(
            1
            for o in getattr(self._controlled, "_orders", {}).values()
            if str(o.status).upper() == "UNKNOWN"
        )
        post = stop_conditions.post_tick(
            sess,
            daily_pnl=daily_pnl,
            recon_critical=recon_critical,
            unknown_orders=unknown_n,
        )
        if post.halt:
            sess = stop_conditions.apply_halt_to_session(sess, post)

        hb = now.isoformat()
        sess = merge_session_update(
            sess,
            {"heartbeat_at": hb, "runtime_phase": "POST_TICK"},
        )
        self._session = sess
        if self._controlled is not None:
            self._controlled._session = sess
        self._last_tick_at = hb

        if self._writer is not None:
            try:
                self._writer.write_runtime_tick(
                    account_id=sess.account_id,
                    tick_id=tick_id,
                    payload={
                        "tick_id": tick_id,
                        "session_id": sess.session_id,
                        "intents_seen": len(intents),
                        "orders_submitted": submitted,
                        "as_of": hb,
                        "metadata": meta,
                    },
                )
            except Exception:
                pass

        latency_ms = (time.monotonic() - t0) * 1000.0
        cl_metrics.record_tick(self._ops, account_id=sess.account_id, latency_ms=latency_ms)

        return RuntimeTickResult(
            tick_id=tick_id,
            session_id=sess.session_id,
            intents_seen=len(intents),
            orders_submitted=submitted,
            halted=post.halt or pre.halt,
            stop_reason=sess.stop_reason,
            runtime_phase=sess.runtime_phase,
            metadata={"recon": _recon, **meta},
        )

    def _collect_intents(
        self,
        session: ControlledSession,
        now: datetime,
        meta: Mapping[str, Any],
    ) -> list[OrderIntent]:
        """优先 intent_provider；其次 production_runtime.tick。"""
        if self._intent_provider is not None:
            return list(self._intent_provider(session, now))
        if self._production is not None and self._runtime_id:
            try:
                result = self._production.tick(self._runtime_id, now=now, metadata=dict(meta))
                return list(getattr(result, "order_intents", []) or [])
            except Exception:
                return []
        raw = meta.get("intents") or []
        return [OrderIntent.model_validate(x) if isinstance(x, dict) else x for x in raw]
