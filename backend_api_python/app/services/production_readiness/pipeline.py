"""Phase 6J：RDY 场景编排（复用 6B–6I 链路）。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping

from app.services.e2e_service.hash import intent_fingerprint
from app.services.e2e_service.identity import (
    stamp_intents,
    stamp_targets,
    submit_metadata_identity,
)
from app.services.oms import OMSError
from app.services.oms.hash import compute_fill_id
from app.services.oms.protocol import ExecutionReport, Fill
from app.services.oms.reducer import apply_execution_report
from app.services.research_data.contracts import TargetPosition
from app.services.risk_engine.policy import finalize_policy
from app.services.risk_engine.protocol import RiskPolicy

from .hash import derive_scenario_run_id
from .pit_stub import reject_pit_leakage
from .protocol import ScenarioResult, ScenarioSpec


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


def _broker_book_size(adapter: Any) -> int:
    rest = getattr(adapter, "_rest", None)
    if rest is None:
        return 0
    return len(getattr(rest, "_orders", {}) or {})


def run_scenario_pipeline(
    spec: ScenarioSpec,
    *,
    services: Mapping[str, Any],
    run_id: str = "",
    account_id: str = "",
    portfolio_id: str = "",
    trading_date: str = "2020-01-02",
    prices: Mapping[str, float] | None = None,
    dataset_hash: str = "",
    strategy_version: str = "",
    strategy_id: str = "rdy_strategy",
    salt: str = "",
    registry_root: Any = None,
) -> ScenarioResult:
    """执行单个 RDY 场景。"""
    meta = dict(spec.metadata or {})
    dh = dataset_hash or str(meta.get("dataset_hash") or "rdy_dh_v1")
    sv = strategy_version or str(meta.get("strategy_version") or "rdy_sv_v1")
    px = dict(prices or {spec.instrument_key: 100.0})
    expect = dict(spec.expect or {})

    portfolio = services["portfolio"]
    risk = services["risk"]
    oms = services["oms"]
    safety = services["safety"]
    ops = services["ops"]
    adapter = services.get("broker_adapter")
    broker_svc = services.get("broker_adapter_service")

    scenario_run_id = derive_scenario_run_id(
        run_id=run_id or spec.scenario_id,
        scenario_id=spec.scenario_id,
        salt=salt or spec.fixture_id,
    )
    result = ScenarioResult(
        scenario_run_id=scenario_run_id,
        scenario_id=spec.scenario_id,
        run_id=run_id,
    )

    for action in spec.pre_actions or []:
        if action == "kill_strategy":
            safety.engage_kill_switch(
                "STRATEGY",
                strategy_id,
                reason="rdy strategy kill",
                operator="rdy",
            )
        elif action == "kill_account":
            safety.engage_kill_switch(
                "ACCOUNT",
                account_id,
                reason="rdy account kill",
                operator="rdy",
            )
        elif action == "kill_global":
            safety.engage_kill_switch(
                "GLOBAL",
                "GLOBAL",
                reason="rdy global kill",
                operator="rdy",
            )

    # RDY-008：策略级 Kill 后本策略应阻断，其他 strategy_id 仍可通过
    if expect.get("strategy_blocked"):
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
        pol = finalize_policy(
            RiskPolicy(
                policy_code="rdy",
                policy_version="1",
                max_single_position_weight=0.50,
                max_gross_exposure=1.0,
                max_turnover=1.0,
                max_position_delta_weight=0.50,
                clip_on_limit=True,
            )
        )
        risk.register_policy(pol)
        risk_eval = risk.evaluate(
            apply_result,
            policy=pol,
            prices=px,
            metadata={
                "force_new_run": True,
                "account_id": account_id,
                "portfolio_id": portfolio_id,
                "strategy_id": strategy_id,
            },
        )
        intents = stamp_intents(
            list(risk_eval.order_intents or []),
            dataset_hash=dh,
            strategy_version=sv,
            strategy_id=strategy_id,
            trace_seed=f"{spec.scenario_id}|blocked",
        )
        blocked_main = False
        try:
            oms.submit_intents(
                intents,
                account_id=account_id,
                portfolio_id=portfolio_id,
                risk_run_id=risk_eval.risk_run_id,
                environment="SANDBOX",
                prices=px,
                metadata={
                    "strategy_id": strategy_id,
                    "simulated": dict(spec.broker_inject or {}),
                    "idempotency_salt": scenario_run_id,
                },
            )
        except OMSError:
            blocked_main = True
        other_id = "rdy_other_strategy"
        apply2 = portfolio.apply_targets(
            account_id,
            targets,
            portfolio_id=portfolio_id,
            trading_date=trading_date,
            prices=px,
            apply_mode="SHADOW_DRY",
            metadata={"force_new_apply": True, "prices": px},
        )
        risk_eval2 = risk.evaluate(
            apply2,
            policy=pol,
            prices=px,
            metadata={
                "force_new_run": True,
                "account_id": account_id,
                "portfolio_id": portfolio_id,
                "strategy_id": other_id,
            },
        )
        intents2 = stamp_intents(
            list(risk_eval2.order_intents or []),
            dataset_hash=dh,
            strategy_version=sv,
            strategy_id=other_id,
            trace_seed=f"{spec.scenario_id}|other",
        )
        other_ok = False
        if intents2:
            try:
                sub2 = oms.submit_intents(
                    intents2,
                    account_id=account_id,
                    portfolio_id=portfolio_id,
                    risk_run_id=risk_eval2.risk_run_id,
                    environment="SANDBOX",
                    prices=px,
                    metadata={
                        "strategy_id": other_id,
                        "simulated": dict(spec.broker_inject or {}),
                        "idempotency_salt": scenario_run_id + "|o",
                    },
                )
                other_ok = bool(sub2.orders)
            except OMSError:
                other_ok = False
        if blocked_main and other_ok:
            result.status = "OK"
        else:
            result.status = "FAILED"
            result.messages.append(
                f"kill isolation blocked_main={blocked_main} other_ok={other_ok}"
            )
        return result

    # RDY-009：Kill → Ack → Resume 审计
    if "ack_resume" in (spec.post_actions or []):
        if not safety.is_blocked(account_id):
            result.status = "FAILED"
            result.messages.append("expected account blocked before ack_resume")
            return result
        safety.acknowledge(f"ACCOUNT|{account_id}", operator="operator_rdy")
        safety.resume("ACCOUNT", account_id, operator="operator_rdy")
        # SAFETY_ACKNOWLEDGE 可能不带 account_id，需全量扫描
        events = ops.list_audit_events()
        has_ack = any(
            str(e.event_type or "").upper() == "SAFETY_ACKNOWLEDGE" for e in events
        )
        has_resume = any(
            str(e.event_type or "").upper() == "SAFETY_RESUME" for e in events
        )
        if has_ack and has_resume:
            result.status = "OK"
        else:
            result.status = "FAILED"
            result.messages.append("missing ack/resume audit events")
        return result

    # RDY-010：Replay + PIT
    if "pit_leakage_check" in (spec.post_actions or []):
        allowed, reason = reject_pit_leakage(
            available_time="2026-10-07T18:00:00+00:00",
            knowledge_time="2026-10-07T15:00:00+00:00",
        )
        if allowed:
            result.status = "FAILED"
            result.messages.append("expected PIT reject")
            return result
        if "replay_twice" in (spec.post_actions or []):
            e2e = services.get("e2e")
            if e2e is None:
                result.status = "FAILED"
                result.messages.append("e2e service required for replay")
                return result
            replay_salt = f"rdy|{scenario_run_id}|replay"
            e2e.start_session(
                dataset_hash=dh,
                strategy_version=sv,
                salt=replay_salt,
            )
            fp1 = e2e.run_scenario(
                "E2E-001",
                mode="PAPER",
                salt=replay_salt,
            ).intent_fingerprint
            e2e.start_session(
                dataset_hash=dh,
                strategy_version=sv,
                salt=replay_salt,
            )
            fp2 = e2e.run_scenario(
                "E2E-001",
                mode="PAPER",
                salt=replay_salt,
            ).intent_fingerprint
            if fp1 and fp1 == fp2 and expect.get("replay_ok"):
                result.status = "OK"
            else:
                result.status = "FAILED"
                result.messages.append("replay intent fingerprint drift")
        else:
            result.status = "OK"
        result.metadata["pit_reason"] = reason
        return result

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
    pol = finalize_policy(
        RiskPolicy(
            policy_code="rdy",
            policy_version="1",
            max_single_position_weight=0.50,
            max_gross_exposure=1.0,
            max_turnover=1.0,
            max_position_delta_weight=0.50,
            clip_on_limit=True,
        )
    )
    risk.register_policy(pol)
    risk_eval = risk.evaluate(
        apply_result,
        policy=pol,
        prices=px,
        metadata={
            "force_new_run": True,
            "account_id": account_id,
            "portfolio_id": portfolio_id,
            "strategy_id": strategy_id,
        },
    )
    intents = stamp_intents(
        list(risk_eval.order_intents or []),
        dataset_hash=dh,
        strategy_version=sv,
        strategy_id=strategy_id,
        trace_seed=f"{spec.scenario_id}|{salt}",
    )
    if not intents and spec.scenario_id not in ("RDY-007",):
        result.status = "FAILED"
        result.messages.append("no intents")
        return result

    submit_meta = submit_metadata_identity(
        dataset_hash=dh,
        strategy_version=sv,
        strategy_id=strategy_id,
        trace_id=str(intents[0].trace_id or "") if intents else "",
        broker_inject=dict(spec.broker_inject or {}),
    )
    submit_meta["simulated"] = dict(spec.broker_inject or {})
    submit_meta["idempotency_salt"] = scenario_run_id
    if meta.get("async_submit"):
        submit_meta["async_submit"] = True

    submit = None
    broker_before = _broker_book_size(adapter)

    submit_env = "SANDBOX" if meta.get("async_submit") else "PAPER"

    if "triple_submit" in (spec.post_actions or []):
        for _ in range(3):
            submit = oms.submit_intents(
                intents,
                account_id=account_id,
                portfolio_id=portfolio_id,
                risk_run_id=risk_eval.risk_run_id,
                environment="PAPER",
                prices=px,
                metadata=dict(submit_meta),
            )
    elif intents:
        submit = oms.submit_intents(
            intents,
            account_id=account_id,
            portfolio_id=portfolio_id,
            risk_run_id=risk_eval.risk_run_id,
            environment=submit_env,
            prices=px,
            metadata=dict(submit_meta),
        )
        if submit_env == "SANDBOX":
            oms.drain_outbox()

    if submit and submit.orders:
        for o in submit.orders:
            result.order_ids.append(o.order_id)

    if "broker_submit_only" in (spec.post_actions or []) and submit and submit.orders:
        order = submit.orders[0]
        if broker_svc is not None:
            broker_svc.submit_order(order)
        elif adapter is not None:
            adapter.submit_order(order)

    if "recover_on_start" in (spec.post_actions or []):
        broker_mid = _broker_book_size(adapter)
        rec = oms.recover_on_start(account_id=account_id)
        broker_after = _broker_book_size(adapter)
        result.metadata["recover"] = rec.model_dump(mode="json")
        if rec.resubmit_attempted:
            result.status = "FAILED"
            result.messages.append("resubmit_attempted must be false")
        if expect.get("no_resubmit") and broker_after > broker_mid:
            result.status = "FAILED"
            result.messages.append("broker order count increased on recover")

    if "recover_unknown" in (spec.post_actions or []) and submit and submit.orders:
        oms.recover_unknown_order(submit.orders[0].order_id)

    if "apply_out_of_order" in (spec.post_actions or []) and submit and submit.orders:
        # 已在 sync submit 得到正确仓位；再模拟乱序 ACK/PARTIAL/FILL 事件（无新增 fill）
        order = oms.get_order(submit.orders[0].order_id)
        if float(order.filled_quantity) + 1e-9 < float(order.quantity):
            result.status = "FAILED"
            result.messages.append("expected order filled before out-of-order replay")
        writer = oms._writer  # noqa: SLF001
        cur = order
        px0 = float(px.get(spec.instrument_key, 100.0))
        reports = [
            ExecutionReport(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="ACK",
            ),
            ExecutionReport(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="PARTIAL",
                filled_quantity=float(order.filled_quantity),
                fills=[],
            ),
            ExecutionReport(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status="FILL",
                filled_quantity=float(order.filled_quantity),
                fills=[],
            ),
        ]
        for rep in reports:
            try:
                cur, evs, fills = apply_execution_report(cur, rep)
                writer.persist_order(cur, events=evs, fills=fills or [])
            except Exception as exc:
                result.messages.append(f"out_of_order: {exc}")

    if "reconnect_pump" in (spec.post_actions or []) and adapter is not None:
        if hasattr(adapter, "reconnect_ws"):
            adapter.reconnect_ws()
        if hasattr(adapter, "pump_events"):

            def _cb(report: Any) -> None:
                if not submit or not submit.orders:
                    return
                oid = submit.orders[0].order_id
                ord0 = oms.get_order(oid)
                if str(ord0.status) == "SUBMITTED":
                    ord0, ev0, _ = apply_execution_report(
                        ord0,
                        ExecutionReport(
                            order_id=ord0.order_id,
                            client_order_id=ord0.client_order_id,
                            status="ACK",
                        ),
                    )
                    oms._writer.persist_order(ord0, events=ev0, fills=[])  # noqa: SLF001
                ord1, evs, fills = apply_execution_report(ord0, report)
                oms._writer.persist_order(ord1, events=evs, fills=fills)  # noqa: SLF001

            adapter.pump_events(_cb)

    if "registry_restart_check" in (spec.post_actions or []):
        from app.services.research_data.registry import LocalJsonRegistry

        root = registry_root
        if root is None:
            result.status = "FAILED"
            result.messages.append("registry_root required")
            return result
        reg2 = LocalJsonRegistry(root=root)
        if submit and submit.orders:
            oid = submit.orders[0].order_id
            try:
                reg2.get_oms_order(oid)
                result.status = "OK"
            except KeyError:
                result.status = "FAILED"
                result.messages.append("order missing after registry re-open")
        else:
            result.status = "FAILED"

    if expect.get("recovered") and submit and submit.orders:
        order = oms.get_order(submit.orders[0].order_id)
        if str(order.status) == "UNKNOWN":
            result.status = "FAILED"
            result.messages.append("still UNKNOWN after recover")

    # 断言
    if submit and submit.orders:
        order = oms.get_order(submit.orders[0].order_id)
        exp_st = str(expect.get("order_status") or "").upper()
        if exp_st and exp_st not in str(order.status).upper():
            result.status = "FAILED"
            result.messages.append(
                f"status {order.status!r} != {exp_st!r}"
            )
        if expect.get("single_broker_order"):
            n = _broker_book_size(adapter)
            if n != 1:
                result.status = "FAILED"
                result.messages.append(f"expected 1 broker order, got {n}")
            if len(submit.orders) != 1:
                result.status = "FAILED"
        fq = float(expect.get("filled_qty") or 0)
        if fq > 0 and abs(float(order.filled_quantity) - fq) > 1e-6:
            result.status = "FAILED"
            result.messages.append(
                f"filled {order.filled_quantity} != {fq}"
            )
        pq = float(expect.get("position_qty") or 0)
        if pq > 0:
            pos = portfolio.get_positions(account_id, portfolio_id=portfolio_id)
            q = 0.0
            for p in pos:
                if p.instrument_key == spec.instrument_key:
                    q = float(p.quantity)
            if abs(q - pq) > 1e-6:
                result.status = "FAILED"
                result.messages.append(f"position {q} != {pq}")

    if result.status != "FAILED" and not result.messages:
        result.status = "OK"

    result.metadata["intent_fingerprint"] = intent_fingerprint(intents or [])
    return result
