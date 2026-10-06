"""Risk evaluate 编排。"""

from __future__ import annotations

from typing import Any, Sequence

from .aggregate import aggregate_decision
from .events import build_events, build_snapshot
from .hash import (
    compute_idempotency_key,
    deltas_fingerprint,
    derive_risk_run_id,
)
from .mapper import decision_to_intents
from .policy import finalize_policy
from .protocol import RiskContext, RiskEvaluateResult
from .rules import default_rules
from .writers import RiskWriter


def run_evaluate(
    context: RiskContext,
    *,
    writer: RiskWriter,
    registry: Any,
    rules: Sequence[Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RiskEvaluateResult:
    """执行规则 → 聚合 → OrderIntent → 持久化。"""
    meta = dict(metadata or {})
    context = context.model_copy(
        update={"policy": finalize_policy(context.policy)}
    )
    ikey = compute_idempotency_key(
        account_id=context.account_id,
        portfolio_id=context.portfolio_id,
        trading_date=context.trading_date,
        apply_id=context.apply_id,
        policy_hash=context.policy.policy_hash,
        deltas_fingerprint=deltas_fingerprint(context.deltas),
    )
    if not meta.get("force_new_run"):
        getter = getattr(registry, "get_risk_run_by_idempotency", None)
        if getter is not None:
            try:
                existing = getter(ikey)
                return RiskEvaluateResult(
                    risk_run_id=existing.risk_run_id,
                    idempotency_key=ikey,
                    policy_hash=existing.policy_hash,
                    verdict=existing.verdict,  # type: ignore[arg-type]
                    reused=True,
                    status="SKIPPED_IDEMPOTENT",
                    metadata={
                        "account_id": existing.account_id,
                        "portfolio_id": existing.portfolio_id,
                        "apply_id": existing.apply_id,
                        "trading_date": existing.trading_date,
                        "reused": True,
                    },
                )
            except KeyError:
                pass

    run_id = derive_risk_run_id(ikey)
    rule_set = list(rules) if rules is not None else default_rules()
    results = []
    for rule in rule_set:
        try:
            results.extend(rule.evaluate(context))
        except Exception as exc:
            from .protocol import RiskResult

            results.append(
                RiskResult(
                    rule_code=getattr(rule, "code", "UNKNOWN"),
                    decision="ERROR",
                    message=str(exc)[:300],
                )
            )

    decision = aggregate_decision(context, results)
    intents = decision_to_intents(
        decision,
        policy=context.policy,
        trading_date=context.trading_date,
        idempotency_key=ikey,
    )
    events = build_events(risk_run_id=run_id, decision=decision)
    snapshot = build_snapshot(
        risk_run_id=run_id, context=context, decision=decision
    )
    result = RiskEvaluateResult(
        risk_run_id=run_id,
        idempotency_key=ikey,
        policy_hash=context.policy.policy_hash,
        verdict=decision.verdict,
        status="OK",
        decision=decision,
        adjusted_deltas=list(decision.adjusted_deltas),
        order_intents=intents,
        violations=list(decision.violations),
        snapshot=snapshot,
        events=events,
        metadata={
            "account_id": context.account_id,
            "portfolio_id": context.portfolio_id,
            "apply_id": context.apply_id,
            "trading_date": context.trading_date,
            "runtime_id": context.runtime_id,
            "bundle_hash": context.bundle_hash,
            "risk_run_id": run_id,
            "policy_hash": context.policy.policy_hash,
        },
    )
    writer.write_run(result)
    return result
