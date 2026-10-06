"""单条规则求值 → 可选 TradingGateDecision 片段。"""

from __future__ import annotations

from typing import Any, Optional

from ..protocol import SafetyContext, SafetyRule, TradingGateDecision
from ..rate_limiter import OrderRateLimiter


def _dec(
    rule: SafetyRule,
    *,
    scope_id: str,
    reason: str,
    trigger: float,
    decision: str | None = None,
    scope: str | None = None,
    actions: list | None = None,
) -> TradingGateDecision:
    return TradingGateDecision(
        decision=(decision or rule.action),  # type: ignore[arg-type]
        scope=(scope or rule.scope),  # type: ignore[arg-type]
        scope_id=scope_id,
        rule_ids=[rule.rule_id],
        reason=reason,
        actions=list(actions or []),
        metadata={"trigger_value": trigger, "threshold": rule.threshold},
    )


def eval_daily_loss(
    ctx: SafetyContext, rule: SafetyRule
) -> Optional[TradingGateDecision]:
    if not rule.enabled:
        return None
    # Net Daily P&L %；阈值为负（如 -0.02）
    if float(ctx.net_daily_pnl_pct) <= float(rule.threshold):
        return _dec(
            rule,
            scope_id=ctx.account_id,
            reason=f"daily loss {ctx.net_daily_pnl_pct} <= {rule.threshold}",
            trigger=float(ctx.net_daily_pnl_pct),
        )
    return None


def eval_max_drawdown(
    ctx: SafetyContext, rule: SafetyRule
) -> Optional[TradingGateDecision]:
    if not rule.enabled:
        return None
    if float(ctx.drawdown_pct) >= float(rule.threshold):
        return _dec(
            rule,
            scope_id=ctx.account_id,
            reason=f"drawdown {ctx.drawdown_pct} >= {rule.threshold}",
            trigger=float(ctx.drawdown_pct),
        )
    return None


def eval_position_limit(
    ctx: SafetyContext, rule: SafetyRule
) -> Optional[TradingGateDecision]:
    if not rule.enabled:
        return None
    signed = float(ctx.quantity) if str(ctx.side).upper() == "BUY" else -float(
        ctx.quantity
    )
    projected = (
        float(ctx.current_position_qty)
        + float(ctx.open_order_qty)
        + float(ctx.pending_order_qty)
        + signed
    )
    if abs(projected) > float(rule.threshold):
        return _dec(
            rule,
            scope_id=ctx.account_id,
            reason=f"projected position {projected} > {rule.threshold}",
            trigger=float(projected),
        )
    return None


def eval_order_notional(
    ctx: SafetyContext, rule: SafetyRule
) -> Optional[TradingGateDecision]:
    if not rule.enabled:
        return None
    notional = float(ctx.notional) or abs(float(ctx.quantity) * float(ctx.price))
    if notional > float(rule.threshold):
        return _dec(
            rule,
            scope_id=ctx.account_id,
            reason=f"notional {notional} > {rule.threshold}",
            trigger=notional,
        )
    return None


def eval_order_rate(
    ctx: SafetyContext,
    rule: SafetyRule,
    limiter: OrderRateLimiter,
) -> Optional[TradingGateDecision]:
    if not rule.enabled:
        return None
    max_sec = float(rule.threshold)
    max_min = float((rule.metadata or {}).get("max_per_minute") or 100.0)
    halt_sec = float((rule.metadata or {}).get("halt_per_second") or 40.0)
    ok, reason, trigger = limiter.check(
        ctx.account_id,
        strategy_id=ctx.strategy_id,
        max_per_second=max_sec,
        max_per_minute=max_min,
    )
    if ok:
        return None
    # 严重超限 → Strategy HALT
    per_sec, _ = limiter.counts(ctx.account_id, strategy_id=ctx.strategy_id)
    if per_sec > halt_sec:
        return _dec(
            rule,
            scope_id=ctx.strategy_id or ctx.account_id,
            reason=reason + " → strategy halt",
            trigger=trigger,
            decision="HALT",
            scope="STRATEGY",
        )
    return _dec(
        rule,
        scope_id=ctx.account_id,
        reason=reason,
        trigger=trigger,
    )


def eval_recon_critical(
    ctx: SafetyContext, rule: SafetyRule
) -> Optional[TradingGateDecision]:
    if not rule.enabled:
        return None
    if ctx.recon_critical:
        return _dec(
            rule,
            scope_id=ctx.account_id,
            reason="reconciliation CRITICAL open",
            trigger=1.0,
        )
    return None


def eval_broker_disconnect(
    ctx: SafetyContext, rule: SafetyRule
) -> Optional[TradingGateDecision]:
    if not rule.enabled:
        return None
    if not ctx.broker_connected:
        return _dec(
            rule,
            scope_id=ctx.account_id,
            reason="broker disconnected",
            trigger=1.0,
        )
    return None


def eval_market_data_stale(
    ctx: SafetyContext, rule: SafetyRule
) -> Optional[TradingGateDecision]:
    if not rule.enabled:
        return None
    if float(ctx.market_data_age_sec) > float(rule.threshold):
        return _dec(
            rule,
            scope_id=ctx.account_id,
            reason=f"market data stale {ctx.market_data_age_sec}s > {rule.threshold}",
            trigger=float(ctx.market_data_age_sec),
        )
    return None


def eval_strategy_error(
    ctx: SafetyContext, rule: SafetyRule
) -> Optional[TradingGateDecision]:
    if not rule.enabled:
        return None
    if int(ctx.strategy_error_count) >= int(rule.threshold):
        return _dec(
            rule,
            scope_id=ctx.strategy_id or ctx.account_id,
            reason=f"strategy errors {ctx.strategy_error_count} >= {rule.threshold}",
            trigger=float(ctx.strategy_error_count),
            scope="STRATEGY",
            decision="HALT",
        )
    return None


def eval_system_health(
    ctx: SafetyContext, rule: SafetyRule
) -> Optional[TradingGateDecision]:
    if not rule.enabled:
        return None
    if not ctx.system_healthy:
        return _dec(
            rule,
            scope_id="GLOBAL",
            reason="system health failure",
            trigger=1.0,
            scope="GLOBAL",
            decision="EMERGENCY",
            actions=["CANCEL_OPEN_ORDERS"],
        )
    return None
