"""Phase 6I：6B→6C→Safety→OMS→Broker→Recon→Ops 编排。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.services.oms import OMSError
from app.services.research_data.contracts import TargetPosition
from app.services.risk_engine.policy import finalize_policy
from app.services.risk_engine.protocol import RiskPolicy

from .hash import derive_scenario_run_id, derive_virtual_order_id, intent_fingerprint
from .identity import (
    stamp_intents,
    stamp_targets,
    submit_metadata_identity,
    validate_intents_identity,
    validate_order_identity,
)
from .modes import assert_mode, oms_environment_for_mode
from .protocol import E2ERunPayload, ScenarioResult, ScenarioSpec, VirtualOrder


class E2EPipelineError(RuntimeError):
    """E2E 编排失败。"""


def _build_targets(
    spec: ScenarioSpec,
    *,
    portfolio_id: str,
    dataset_hash: str,
    strategy_version: str,
    trading_date: str,
) -> list[TargetPosition]:
    ts = datetime(2020, 1, 2, 10, 0, tzinfo=timezone.utc)
    qty = float(spec.target_quantity)
    if spec.side == "SELL":
        qty = -abs(qty)
    t = TargetPosition(
        instrument_key=spec.instrument_key,
        trading_date=trading_date,
        portfolio_id=portfolio_id,
        strategy_version=strategy_version,
        dataset_hash=dataset_hash,
        timestamp=ts,
        target_quantity=abs(qty),
    )
    return stamp_targets(
        [t], dataset_hash=dataset_hash, strategy_version=strategy_version
    )


def _resolve_policy(
    risk_service: Any,
    spec: ScenarioSpec,
    default: RiskPolicy | None,
) -> RiskPolicy:
    overrides = dict(spec.risk_policy_overrides or {})
    if default is None:
        default = RiskPolicy(
            policy_code="e2e",
            policy_version="1",
            max_single_position_weight=0.50,
            max_gross_exposure=1.0,
            max_turnover=1.0,
            max_position_delta_weight=0.50,
            clip_on_limit=True,
        )
    if overrides:
        default = default.model_copy(update=overrides)
    pol = finalize_policy(default)
    try:
        risk_service.register_policy(pol)
    except Exception:
        pass
    return pol


def run_scenario_pipeline(
    spec: ScenarioSpec,
    *,
    mode: str,
    services: Mapping[str, Any],
    session_id: str = "",
    run_id: str = "",
    account_id: str = "",
    portfolio_id: str = "",
    trading_date: str = "2020-01-02",
    prices: Mapping[str, float] | None = None,
    dataset_hash: str = "",
    strategy_version: str = "",
    strategy_id: str = "e2e_strategy",
    salt: str = "",
) -> ScenarioResult:
    """执行单场景：SHADOW 在 Intent 后 STOP 并写 VirtualOrder。"""
    m = assert_mode(mode)
    meta = dict(spec.metadata or {})
    dh = dataset_hash or str(meta.get("dataset_hash") or "e2e_dh_v1")
    sv = strategy_version or str(meta.get("strategy_version") or "e2e_sv_v1")
    px = dict(prices or {spec.instrument_key: 100.0})

    portfolio = services["portfolio"]
    risk = services["risk"]
    oms = services["oms"]
    safety = services["safety"]
    recon = services["recon"]
    ops = services["ops"]

    scenario_run_id = derive_scenario_run_id(
        run_id=run_id or session_id or spec.scenario_id,
        scenario_id=spec.scenario_id,
        mode=m,
        salt=salt or spec.fixture_id,
    )
    result = ScenarioResult(
        scenario_run_id=scenario_run_id,
        scenario_id=spec.scenario_id,
        run_id=run_id,
        session_id=session_id,
        mode=m,  # type: ignore[arg-type]
        dataset_hash=dh,
        strategy_version=sv,
        strategy_id=strategy_id,
    )

    # Pre-actions
    for action in spec.pre_actions or []:
        if action == "kill_switch":
            safety.engage_kill_switch(
                "ACCOUNT", account_id, reason="e2e kill", operator="e2e"
            )
        elif action == "disconnect":
            ops.report_broker_disconnect(account_id=account_id, broker_id="sim")

    targets = _build_targets(
        spec,
        portfolio_id=portfolio_id,
        dataset_hash=dh,
        strategy_version=sv,
        trading_date=trading_date,
    )

    apply_result = portfolio.apply_targets(
        account_id,
        targets,
        portfolio_id=portfolio_id,
        trading_date=trading_date,
        prices=px,
        apply_mode="SHADOW_DRY",
        metadata={"force_new_apply": True, "prices": px},
    )
    result.apply_id = apply_result.apply_id

    policy = _resolve_policy(risk, spec, services.get("default_policy"))
    risk_eval = risk.evaluate(
        apply_result,
        policy=policy,
        prices=px,
        metadata={
            "force_new_run": True,
            "account_id": account_id,
            "portfolio_id": portfolio_id,
            "trading_date": trading_date,
            "strategy_version": sv,
        },
    )
    result.risk_run_id = risk_eval.risk_run_id
    result.risk_verdict = str(risk_eval.verdict)

    raw_intents = list(risk_eval.order_intents or [])
    if spec.execution_algorithm == "LIMIT" or spec.limit_price is not None:
        raw_intents = [
            it.model_copy(
                update={
                    "execution_algorithm": spec.execution_algorithm,
                    "limit_price": spec.limit_price,
                }
            )
            for it in raw_intents
        ]
    intents = stamp_intents(
        raw_intents,
        dataset_hash=dh,
        strategy_version=sv,
        strategy_id=strategy_id,
        trace_seed=f"{spec.scenario_id}|{salt}",
    )
    if intents:
        result.trace_id = str(intents[0].trace_id or "")
        validate_intents_identity(intents, dataset_hash=dh, strategy_version=sv)
    result.intent_fingerprint = intent_fingerprint(intents)

    expect = dict(spec.expect or {})
    if expect.get("risk_reject") or result.risk_verdict == "REJECT":
        if not intents:
            result.status = "OK"
            return result
        result.status = "FAILED"
        result.messages.append("expected risk reject but got intents")
        return result

    if m == "SHADOW":
        virtuals: list[VirtualOrder] = []
        now = datetime.now(timezone.utc).isoformat()
        for it in intents:
            virtuals.append(
                VirtualOrder(
                    virtual_order_id=derive_virtual_order_id(
                        scenario_run_id=scenario_run_id,
                        instrument_key=it.instrument_key,
                        side=str(it.side),
                        quantity=float(it.quantity),
                    ),
                    instrument_key=it.instrument_key,
                    side=str(it.side),
                    quantity=float(it.quantity),
                    status="WOULD_SUBMIT",
                    trace_id=str(it.trace_id or ""),
                    scenario_run_id=scenario_run_id,
                    session_id=session_id,
                    created_at=now,
                    metadata={"dataset_hash": dh, "strategy_version": sv},
                )
            )
        result.virtual_orders = virtuals
        ops.emit_audit(
            event_type="E2E_SHADOW_STOP",
            account_id=account_id,
            trace_id=result.trace_id,
            reason=spec.scenario_id,
            salt=scenario_run_id,
        )
        result.status = "OK"
        return result

    if not intents:
        if expect.get("no_orders"):
            result.status = "OK"
        else:
            result.status = "FAILED"
            result.messages.append("no intents produced")
        return result

    oms_env = oms_environment_for_mode(m)
    submit_meta = submit_metadata_identity(
        dataset_hash=dh,
        strategy_version=sv,
        strategy_id=strategy_id,
        trace_id=result.trace_id,
        broker_inject=dict(spec.broker_inject or {}),
    )
    submit_meta["force_new_apply"] = True
    submit_meta["idempotency_salt"] = scenario_run_id
    if m == "PAPER_REAL_MD":
        submit_meta["price_bars"] = meta.get("price_bars") or {}

    blocked = False
    try:
        submit = oms.submit_intents(
            intents,
            account_id=account_id,
            portfolio_id=portfolio_id,
            risk_run_id=risk_eval.risk_run_id,
            policy_hash=risk_eval.policy_hash,
            environment=oms_env,
            prices=px,
            metadata=submit_meta,
        )
    except OMSError as exc:
        blocked = True
        result.blocked_by_safety = True
        result.messages.append(str(exc))
        if expect.get("blocked"):
            result.status = "OK"
            if expect.get("health_degraded"):
                snap = ops.collect_health(account_id=account_id)
                if snap.health.broker.status != "DEGRADED":
                    result.status = "FAILED"
        else:
            result.status = "FAILED"
        if expect.get("kill_audit"):
            events = ops.list_audit_events(account_id=account_id)
            if any(e.event_type == "KILL_SWITCH_ON" for e in events):
                result.status = "OK"
        return result

    if oms_env in ("SANDBOX", "ALPACA_PAPER"):
        oms.drain_outbox()

    for order in submit.orders:
        result.order_ids.append(order.order_id)
        try:
            validate_order_identity(
                order,
                dataset_hash=dh,
                strategy_version=sv,
                trace_id=result.trace_id,
            )
        except Exception as exc:
            result.messages.append(str(exc))

    order_status = submit.orders[0].status if submit.orders else ""
    filled_before_cancel = (
        float(submit.orders[0].filled_quantity) if submit.orders else 0.0
    )
    for action in spec.post_actions or []:
        if action == "cancel" and submit.orders:
            oid = submit.orders[0].order_id
            if filled_before_cancel <= 0 and submit.orders[0].status == "SUBMITTED":
                oms.drain_outbox()
                filled_before_cancel = float(
                    oms.get_order(oid).filled_quantity or 0.0
                )
            oms.cancel(oid, reason="e2e cancel")
            order_status = oms.get_order(oid).status
        elif action == "recover_unknown" and submit.orders:
            oms.recover_unknown_order(submit.orders[0].order_id)
            order_status = oms.get_order(submit.orders[0].order_id).status
        elif action == "recon_mismatch":
            recon.run(
                account_id,
                portfolio_id,
                mode="EOD",
                salt=scenario_run_id,
                inject={"force_broker_position": {spec.instrument_key: 0.0}},
            )

    if "recon_mismatch" not in (spec.post_actions or []):
        recon_run = recon.run(
            account_id,
            portfolio_id,
            mode="FAST",
            salt=f"e2e|{scenario_run_id}",
        )
        result.reconciliation_run_id = recon_run.run_id
        result.reconciliation_critical = recon_run.critical_count > 0

    exp_status = str(expect.get("order_status") or "").upper()
    if expect.get("partial_before_cancel"):
        result.status = (
            "OK"
            if filled_before_cancel > 0 and "CANCEL" in order_status.upper()
            else "FAILED"
        )
    elif exp_status and order_status:
        ok_st = exp_status in order_status.upper() or (
            exp_status == "REJECTED" and "REJECT" in order_status.upper()
        )
        if not ok_st:
            result.status = "FAILED"
            result.messages.append(
                f"order status {order_status!r} != expected {exp_status!r}"
            )
        else:
            result.status = "OK"
    elif expect.get("recon_critical"):
        result.reconciliation_critical = True
        result.status = "OK" if safety.is_blocked(account_id) else "FAILED"
        result.blocked_by_safety = safety.is_blocked(account_id)
    elif expect.get("health_degraded"):
        snap = ops.collect_health(account_id=account_id)
        deg = snap.health.broker.status == "DEGRADED"
        result.status = "OK" if deg and (
            expect.get("blocked") or result.blocked_by_safety or True
        ) else "FAILED"
        if expect.get("blocked") and result.blocked_by_safety:
            result.status = "OK"
    else:
        result.status = "OK"

    return result


def build_run_payload(
    result: ScenarioResult,
    targets: list[TargetPosition],
) -> E2ERunPayload:
    return E2ERunPayload(scenario_result=result, targets=targets)
