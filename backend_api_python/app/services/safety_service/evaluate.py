"""Fail-Closed 聚合：UNKNOWN / 异常 → BLOCK_NEW_ORDER。"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from .kill_switch import KillSwitchStore
from .protocol import (
    SafetyContext,
    SafetyRule,
    SafetyState,
    TradingGateDecision,
)
from .rate_limiter import OrderRateLimiter
from .rules import (
    eval_broker_disconnect,
    eval_daily_loss,
    eval_market_data_stale,
    eval_max_drawdown,
    eval_order_notional,
    eval_order_rate,
    eval_position_limit,
    eval_recon_critical,
    eval_strategy_error,
    eval_system_health,
    merge_rules,
)
from .state_machine import is_blocking_state


_DECISION_RANK = {
    "ALLOW": 0,
    "BLOCK_NEW_ORDER": 1,
    "HALT": 2,
    "EMERGENCY": 3,
}


def _worse(a: TradingGateDecision, b: TradingGateDecision) -> TradingGateDecision:
    if _DECISION_RANK.get(b.decision, 0) > _DECISION_RANK.get(a.decision, 0):
        return b
    if a.decision == b.decision:
        # 合并 rule_ids
        rules = list(dict.fromkeys([*a.rule_ids, *b.rule_ids]))
        return a.model_copy(
            update={
                "rule_ids": rules,
                "reason": a.reason or b.reason,
                "actions": list(dict.fromkeys([*a.actions, *b.actions])),
            }
        )
    return a


def evaluate(
    ctx: SafetyContext,
    *,
    rules: Mapping[str, SafetyRule] | Sequence[SafetyRule] | None = None,
    states: Sequence[SafetyState] | None = None,
    kill_switches: KillSwitchStore | None = None,
    rate_limiter: OrderRateLimiter | None = None,
) -> TradingGateDecision:
    """聚合所有规则与 Kill Switch；Fail-Closed。"""
    try:
        return _evaluate_inner(
            ctx,
            rules=rules,
            states=states,
            kill_switches=kill_switches,
            rate_limiter=rate_limiter,
        )
    except Exception as exc:  # noqa: BLE001 — Fail-Closed
        return TradingGateDecision(
            decision="BLOCK_NEW_ORDER",
            scope="ACCOUNT",
            scope_id=ctx.account_id,
            rule_ids=["FAIL_CLOSED"],
            reason=f"safety evaluate unavailable: {exc}",
            fail_closed=True,
        )


def _evaluate_inner(
    ctx: SafetyContext,
    *,
    rules: Mapping[str, SafetyRule] | Sequence[SafetyRule] | None = None,
    states: Sequence[SafetyState] | None = None,
    kill_switches: KillSwitchStore | None = None,
    rate_limiter: OrderRateLimiter | None = None,
) -> TradingGateDecision:
    if not ctx.safety_state_known:
        return TradingGateDecision(
            decision="BLOCK_NEW_ORDER",
            scope="ACCOUNT",
            scope_id=ctx.account_id,
            rule_ids=["FAIL_CLOSED"],
            reason="safety state UNKNOWN",
            fail_closed=True,
        )

    best = TradingGateDecision(
        decision="ALLOW",
        scope="ACCOUNT",
        scope_id=ctx.account_id,
    )

    # 持久化状态阻断
    for st in states or []:
        if is_blocking_state(st.state):
            best = _worse(
                best,
                TradingGateDecision(
                    decision="EMERGENCY"
                    if st.state == "EMERGENCY"
                    else "HALT"
                    if st.state == "HALTED"
                    else "BLOCK_NEW_ORDER",
                    scope=st.scope,  # type: ignore[arg-type]
                    scope_id=st.scope_id,
                    rule_ids=["KILL_SWITCH"]
                    if st.state != "UNKNOWN"
                    else ["FAIL_CLOSED"],
                    reason=st.reason or f"state={st.state}",
                    fail_closed=st.state == "UNKNOWN",
                ),
            )

    # Kill switches
    if kill_switches is not None:
        for scope, sid in (
            ("GLOBAL", "GLOBAL"),
            ("ACCOUNT", ctx.account_id),
            ("STRATEGY", ctx.strategy_id or ""),
        ):
            if not sid and scope == "STRATEGY":
                continue
            ks = kill_switches.get(scope, sid)  # type: ignore[arg-type]
            if ks.engaged:
                best = _worse(
                    best,
                    TradingGateDecision(
                        decision="HALT" if scope != "GLOBAL" else "EMERGENCY",
                        scope=scope,  # type: ignore[arg-type]
                        scope_id=sid,
                        rule_ids=["KILL_SWITCH"],
                        reason=ks.reason or f"kill switch {scope}",
                        actions=["CANCEL_OPEN_ORDERS"]
                        if scope == "GLOBAL"
                        else [],
                    ),
                )

    rule_map = merge_rules(None) if rules is None else (
        rules if isinstance(rules, dict) else {r.rule_id: r for r in rules}
    )
    limiter = rate_limiter or OrderRateLimiter()

    checkers = [
        lambda: eval_daily_loss(ctx, rule_map["DAILY_LOSS_LIMIT"]),
        lambda: eval_max_drawdown(ctx, rule_map["MAX_DRAWDOWN"]),
        lambda: eval_position_limit(ctx, rule_map["POSITION_LIMIT"]),
        lambda: eval_order_notional(ctx, rule_map["ORDER_NOTIONAL_LIMIT"]),
        lambda: eval_order_rate(ctx, rule_map["ORDER_RATE_LIMIT"], limiter),
        lambda: eval_recon_critical(ctx, rule_map["RECONCILIATION_CRITICAL"]),
        lambda: eval_broker_disconnect(ctx, rule_map["BROKER_DISCONNECT"]),
        lambda: eval_market_data_stale(ctx, rule_map["MARKET_DATA_STALE"]),
        lambda: eval_strategy_error(ctx, rule_map["STRATEGY_ERROR"]),
        lambda: eval_system_health(ctx, rule_map["SYSTEM_HEALTH"]),
    ]
    for fn in checkers:
        d = fn()
        if d is not None and d.decision != "ALLOW":
            best = _worse(best, d)

    return best
