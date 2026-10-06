"""decide 周期：组装 SafetyContext → evaluate → 写事件/状态。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .evaluate import evaluate
from .hash import derive_event_id
from .kill_switch import KillSwitchStore
from .protocol import SafetyContext, SafetyEvent, SafetyState, TradingGateDecision
from .rate_limiter import OrderRateLimiter
from .rules import merge_rules
from .sources import SourceFlags
from .state_machine import transition
from .writers import SafetyWriter


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_context(
    account_id: str,
    intent: Any = None,
    *,
    strategy_id: str = "",
    prices: Mapping[str, float] | None = None,
    portfolio_service: Any = None,
    oms_service: Any = None,
    source_flags: SourceFlags | None = None,
    broker_port: Any = None,
    market_data: Any = None,
    inject: Mapping[str, Any] | None = None,
) -> SafetyContext:
    """从 Portfolio/OMS/源端口组装上下文；inject 覆盖便于故障注入。"""
    inj = dict(inject or {})
    flags = source_flags or SourceFlags()
    instrument = ""
    side = "BUY"
    qty = 0.0
    px = 0.0
    if intent is not None:
        instrument = str(getattr(intent, "instrument_key", "") or "")
        side = str(getattr(intent, "side", "BUY") or "BUY")
        qty = float(getattr(intent, "quantity", 0) or 0)
    if prices and instrument:
        px = float(prices.get(instrument) or 0)
    elif intent is not None and getattr(intent, "limit_price", None):
        px = float(intent.limit_price)

    current_qty = 0.0
    open_qty = 0.0
    pending_qty = 0.0
    net_pnl = 0.0
    dd = 0.0
    peak = 0.0
    equity = 0.0

    if portfolio_service is not None and "net_daily_pnl_pct" not in inj:
        try:
            acct = portfolio_service.get_account(account_id)
            cash = float(acct.cash.available_cash)
            mv = float(getattr(acct, "market_value", 0) or 0)
            equity = cash + mv
            peak = float((acct.metadata or {}).get("peak_equity") or equity or 1.0)
            if peak > 0:
                dd = max(0.0, (peak - equity) / peak)
            # stub：metadata.net_daily_pnl_pct 优先
            net_pnl = float((acct.metadata or {}).get("net_daily_pnl_pct") or 0.0)
            pid = str((acct.metadata or {}).get("default_portfolio_id") or "")
            if pid and instrument:
                for p in portfolio_service.get_positions(pid) or []:
                    if p.instrument_key == instrument:
                        current_qty = float(p.quantity)
        except Exception:
            pass

    if oms_service is not None and instrument:
        try:
            for o in oms_service.list_orders(account_id=account_id) or []:
                st = str(getattr(o, "status", "") or "")
                if getattr(o, "instrument_key", "") != instrument:
                    continue
                rem = float(getattr(o, "quantity", 0) or 0) - float(
                    getattr(o, "filled_quantity", 0) or 0
                )
                if st in ("SUBMITTED", "ACKNOWLEDGED", "PARTIALLY_FILLED", "UNKNOWN"):
                    open_qty += rem
                if st == "PENDING_NEW":
                    pending_qty += rem
        except Exception:
            pass

    broker_ok = True
    if broker_port is not None and hasattr(broker_port, "is_connected"):
        broker_ok = bool(broker_port.is_connected())
    elif hasattr(broker_port, "_connected"):
        broker_ok = bool(getattr(broker_port, "_connected", True))

    md_age = 0.0
    if market_data is not None and instrument:
        md_age = float(market_data.age_sec(instrument))

    ctx = SafetyContext(
        account_id=account_id,
        strategy_id=strategy_id,
        instrument_key=instrument,
        side=side,
        quantity=qty,
        price=px,
        notional=abs(qty * px),
        current_position_qty=current_qty,
        open_order_qty=open_qty,
        pending_order_qty=pending_qty,
        net_daily_pnl_pct=net_pnl,
        drawdown_pct=dd,
        peak_equity=peak,
        current_equity=equity,
        recon_critical=account_id in flags.recon_critical_accounts,
        broker_connected=broker_ok,
        market_data_age_sec=md_age,
        strategy_error_count=int(
            flags.strategy_error_counts.get(strategy_id) or 0
        ),
        system_healthy=flags.system_healthy,
        safety_state_known=flags.state_known,
    )
    # inject 覆盖
    for k, v in inj.items():
        if hasattr(ctx, k):
            ctx = ctx.model_copy(update={k: v})
    return ctx


def run_decide(
    account_id: str,
    intent: Any = None,
    *,
    strategy_id: str = "",
    prices: Mapping[str, float] | None = None,
    writer: SafetyWriter,
    kill_switches: KillSwitchStore,
    rate_limiter: OrderRateLimiter,
    source_flags: SourceFlags,
    portfolio_service: Any = None,
    oms_service: Any = None,
    broker_port: Any = None,
    market_data: Any = None,
    rules: Any = None,
    inject: Mapping[str, Any] | None = None,
    record_rate: bool = True,
) -> TradingGateDecision:
    """执行一次 Safety decide 并在阻断时写事件/状态。"""
    ctx = build_context(
        account_id,
        intent,
        strategy_id=strategy_id,
        prices=prices,
        portfolio_service=portfolio_service,
        oms_service=oms_service,
        source_flags=source_flags,
        broker_port=broker_port,
        market_data=market_data,
        inject=inject,
    )

    states: list[SafetyState] = []
    for scope, sid in (
        ("GLOBAL", "GLOBAL"),
        ("ACCOUNT", account_id),
        ("STRATEGY", strategy_id or ""),
    ):
        if not sid and scope == "STRATEGY":
            continue
        try:
            states.append(writer.get_state(scope, sid))
        except KeyError:
            pass

    rule_map = merge_rules(rules) if rules is not None else merge_rules(None)
    decision = evaluate(
        ctx,
        rules=rule_map,
        states=states,
        kill_switches=kill_switches,
        rate_limiter=rate_limiter,
    )

    if record_rate and intent is not None and decision.decision == "ALLOW":
        rate_limiter.record(account_id, strategy_id=strategy_id)

    if decision.decision != "ALLOW":
        _persist_block(
            writer,
            decision=decision,
            ctx=ctx,
        )
    return decision


def _persist_block(
    writer: SafetyWriter,
    *,
    decision: TradingGateDecision,
    ctx: SafetyContext,
) -> None:
    rule = (decision.rule_ids or ["UNKNOWN"])[0]
    bucket = f"{decision.decision}|{round(float((decision.metadata or {}).get('trigger_value') or 0), 4)}"
    eid = derive_event_id(
        rule=rule,
        scope=decision.scope,
        scope_id=decision.scope_id,
        trigger_bucket=bucket,
    )
    # 幂等：已存在则跳过
    if writer.event_exists(eid):
        return

    before = "NORMAL"
    try:
        st = writer.get_state(decision.scope, decision.scope_id)
        before = st.state
    except KeyError:
        st = SafetyState(
            scope=decision.scope,  # type: ignore[arg-type]
            scope_id=decision.scope_id,
            state="NORMAL",
        )

    target = "EMERGENCY" if decision.decision == "EMERGENCY" else (
        "HALTED" if decision.decision in ("HALT", "BLOCK_NEW_ORDER") and decision.decision == "HALT"
        else "HALTED"
        if decision.decision == "HALT"
        else "DEGRADED"
        if decision.decision == "BLOCK_NEW_ORDER"
        else "HALTED"
    )
    # BLOCK_NEW_ORDER from recon → DEGRADED；HALT/EMERGENCY 对应状态
    if decision.decision == "BLOCK_NEW_ORDER":
        target = "DEGRADED"
    elif decision.decision == "HALT":
        target = "HALTED"
    elif decision.decision == "EMERGENCY":
        target = "EMERGENCY"

    try:
        new_st = transition(st, target, reason=decision.reason)  # type: ignore[arg-type]
    except Exception:
        new_st = st.model_copy(
            update={
                "state": target,
                "reason": decision.reason,
                "updated_at": _now(),
            }
        )
    writer.set_state(new_st)

    ev = SafetyEvent(
        event_id=eid,
        scope=decision.scope,  # type: ignore[arg-type]
        scope_id=decision.scope_id,
        rule=rule,
        severity="CRITICAL"
        if decision.decision in ("HALT", "EMERGENCY")
        else "ERROR",
        state_before=before,
        state_after=target,
        reason=decision.reason,
        trigger_value=float((decision.metadata or {}).get("trigger_value") or 0),
        threshold=float((decision.metadata or {}).get("threshold") or 0),
        created_at=_now(),
        metadata={"actions": list(decision.actions or [])},
    )
    writer.write_event(ev)
