"""可配置规则 vs HardLimits。"""

from __future__ import annotations

from typing import Any, Mapping

from ..protocol import DEFAULT_HARD_LIMITS, HardLimits, SafetyRule


class RuleConfigError(ValueError):
    """配置突破硬上限。"""


def default_rules(hard: HardLimits | None = None) -> list[SafetyRule]:
    """P0 默认规则集（阈值严于或等于 hard）。"""
    h = hard or DEFAULT_HARD_LIMITS
    return [
        SafetyRule(
            rule_id="DAILY_LOSS_LIMIT",
            enabled=True,
            threshold=-0.02,
            action="HALT",
        ),
        SafetyRule(
            rule_id="MAX_DRAWDOWN",
            enabled=True,
            threshold=0.10,
            action="HALT",
        ),
        SafetyRule(
            rule_id="POSITION_LIMIT",
            enabled=True,
            threshold=10_000.0,
            action="BLOCK_NEW_ORDER",
        ),
        SafetyRule(
            rule_id="ORDER_NOTIONAL_LIMIT",
            enabled=True,
            threshold=100_000.0,
            action="BLOCK_NEW_ORDER",
        ),
        SafetyRule(
            rule_id="ORDER_RATE_LIMIT",
            enabled=True,
            threshold=10.0,  # per second
            action="BLOCK_NEW_ORDER",
            metadata={"max_per_minute": 100.0, "halt_per_second": 40.0},
        ),
        SafetyRule(
            rule_id="RECONCILIATION_CRITICAL",
            enabled=True,
            threshold=1.0,
            action="BLOCK_NEW_ORDER",
        ),
        SafetyRule(
            rule_id="BROKER_DISCONNECT",
            enabled=True,
            threshold=1.0,
            action="BLOCK_NEW_ORDER",
        ),
        SafetyRule(
            rule_id="MARKET_DATA_STALE",
            enabled=True,
            threshold=5.0,  # seconds
            action="BLOCK_NEW_ORDER",
        ),
        SafetyRule(
            rule_id="STRATEGY_ERROR",
            enabled=True,
            threshold=5.0,  # consecutive errors
            action="HALT",
            scope="STRATEGY",
        ),
        SafetyRule(
            rule_id="SYSTEM_HEALTH",
            enabled=True,
            threshold=1.0,
            action="EMERGENCY",
        ),
    ]


def validate_rule_against_hard(
    rule: SafetyRule, hard: HardLimits | None = None
) -> None:
    """可配置不得松于 hard ceiling。"""
    h = hard or DEFAULT_HARD_LIMITS
    rid = str(rule.rule_id).upper()
    th = float(rule.threshold)
    if rid == "ORDER_NOTIONAL_LIMIT" and th > h.max_order_notional:
        raise RuleConfigError(
            f"notional {th} exceeds hard {h.max_order_notional}"
        )
    if rid == "ORDER_RATE_LIMIT" and th > h.max_orders_per_second:
        raise RuleConfigError(
            f"rate/sec {th} exceeds hard {h.max_orders_per_second}"
        )
    if rid == "DAILY_LOSS_LIMIT" and th < h.max_daily_loss_pct:
        # threshold 更负 = 更松；禁止
        raise RuleConfigError(
            f"daily loss {th} looser than hard {h.max_daily_loss_pct}"
        )
    if rid == "MAX_DRAWDOWN" and th > h.max_drawdown_pct:
        raise RuleConfigError(
            f"drawdown {th} exceeds hard {h.max_drawdown_pct}"
        )
    if rid == "POSITION_LIMIT" and th > h.max_position_qty:
        raise RuleConfigError(
            f"position {th} exceeds hard {h.max_position_qty}"
        )
    if rid == "MARKET_DATA_STALE" and th > h.max_market_data_staleness_sec:
        raise RuleConfigError(
            f"staleness {th} exceeds hard {h.max_market_data_staleness_sec}"
        )


def merge_rules(
    overrides: Mapping[str, Any] | list[SafetyRule] | None = None,
    *,
    hard: HardLimits | None = None,
) -> dict[str, SafetyRule]:
    """默认 + 覆盖；校验 hard。"""
    by_id = {r.rule_id: r for r in default_rules(hard)}
    if overrides is None:
        return by_id
    items: list[SafetyRule] = []
    if isinstance(overrides, list):
        items = list(overrides)
    else:
        for k, v in overrides.items():
            if isinstance(v, SafetyRule):
                items.append(v)
            else:
                payload = dict(v) if isinstance(v, Mapping) else {}
                payload.setdefault("rule_id", k)
                items.append(SafetyRule.model_validate(payload))
    for r in items:
        validate_rule_against_hard(r, hard)
        by_id[r.rule_id] = r
    return by_id
