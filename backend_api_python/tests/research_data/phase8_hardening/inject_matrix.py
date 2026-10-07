"""Failure injection matrix — compose existing 8C–8H Fake injects."""

from __future__ import annotations

from pathlib import Path

from app.services.production_research_feedback.runner import ProductionResearchFeedbackError
from app.services.strategy_promotion.runner import PromotionError

from performance_feedback_golden.golden import (
    golden_actual_drift_inject,
    golden_baseline_metrics_inject,
    make_feedback_env,
    seed_completed_promotion,
)
from production_research_feedback_golden.golden import golden_bad_pit_lineage_inject
from promotion_pipeline_golden.golden import make_promotion_env, seed_promoted_registry
from strategy_candidate_golden.golden import REGISTRY_VERSION, STRATEGY_CODE
from strategy_guardrails_golden.golden import (
    golden_performance_critical_guardrail_inject,
    golden_recon_emergency_guardrail_inject,
    golden_risk_pause_guardrail_inject,
    golden_slippage_critical_guardrail_inject,
    make_guardrails_env,
    seed_guardrails_baseline,
)
from strategy_monitoring_golden.golden import (
    golden_market_data_critical_inject,
    make_monitoring_env,
    seed_feedback_comparison,
)

from phase8_hardening.fsm_checks import assert_runtime_paused_not_lifecycle_retired


def run_failure_inject_matrix(tmp: Path) -> dict[str, bool]:
    checks: dict[str, bool] = {}

    mon, fb, promo, cand, reg, val, _ = make_monitoring_env(tmp / "m_market")
    seed_feedback_comparison(fb, promo, cand, reg, val, idempotency_key="m_market")
    health = mon.collect_and_evaluate(
        STRATEGY_CODE, inject=golden_market_data_critical_inject(), session_id="mx1"
    )
    checks["market_data_critical"] = health.overall == "CRITICAL"

    gr, mon2, fb2, promo2, cand2, reg2, val2, safety, _gov = make_guardrails_env(
        tmp / "m_guard"
    )
    seed_guardrails_baseline(mon2, fb2, promo2, cand2, reg2, val2, idempotency_key="m_gr")
    gr.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_recon_emergency_guardrail_inject(),
        session_id="mx2",
    )
    checks["recon_emergency_safety_stop"] = (
        gr.get_runtime_state(STRATEGY_CODE).runtime_status == "STOPPED" and bool(safety.halts)
    )

    gr2, mon3, fb3, promo3, cand3, reg3, val3, _s2, _gov2 = make_guardrails_env(tmp / "m_risk")
    seed_guardrails_baseline(mon3, fb3, promo3, cand3, reg3, val3, idempotency_key="m_risk")
    res = gr2.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_risk_pause_guardrail_inject(),
        session_id="mx3",
    )
    rt = gr2.get_runtime_state(STRATEGY_CODE)
    checks["risk_critical_pause"] = "PAUSE" in res.actions_applied and rt.runtime_status == "PAUSED"
    assert_runtime_paused_not_lifecycle_retired(
        runtime_status=rt.runtime_status,
        lifecycle_phase=rt.lifecycle_phase,
    )

    gr3, mon4, fb4, promo4, cand4, reg4, val4, _s3, gov3 = make_guardrails_env(tmp / "m_slip")
    seed_guardrails_baseline(mon4, fb4, promo4, cand4, reg4, val4, idempotency_key="m_slip")
    res3 = gr3.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_slippage_critical_guardrail_inject(),
        session_id="mx4",
    )
    checks["slippage_throttle"] = (
        "THROTTLE" in res3.actions_applied
        and gr3.get_runtime_state(STRATEGY_CODE).runtime_status == "THROTTLED"
        and bool(gov3._runtime_throttle_log)
    )

    gr4, mon5, fb5, promo5, cand5, reg5, val5, safety4, _gov4 = make_guardrails_env(
        tmp / "m_perf"
    )
    seed_guardrails_baseline(mon5, fb5, promo5, cand5, reg5, val5, idempotency_key="m_perf")
    res4 = gr4.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_performance_critical_guardrail_inject(),
        session_id="mx5",
    )
    incs = gr4.list_incidents(STRATEGY_CODE)
    checks["perf_critical_review_no_auto_stop"] = (
        "STOP" not in res4.actions_applied
        and not safety4.halts
        and any(i.status == "REVIEW_REQUIRED" for i in incs)
    )

    from production_research_feedback_golden.golden import make_feedback_env as make_prf_env

    prf, _reg, _dq = make_prf_env(tmp / "m_pit")
    try:
        prf.build_dataset(
            STRATEGY_CODE,
            "PERFORMANCE_FEEDBACK",
            "2025-05-01",
            "2025-06-01",
            inject=golden_bad_pit_lineage_inject(),
        )
        checks["bad_pit_quality_gate"] = False
    except ProductionResearchFeedbackError:
        checks["bad_pit_quality_gate"] = True

    fb6, promo6, cand6, reg6, val6, _ = make_feedback_env(tmp / "m_drift")
    pid = seed_completed_promotion(promo6, cand6, reg6, val6, idempotency_key="m_drift")
    base = fb6.freeze_baseline_from_promotion(
        pid, metrics_inject=golden_baseline_metrics_inject()
    )
    run = fb6.run_comparison(
        baseline_id=base.baseline_id,
        actual_source="SHADOW",
        window_start="2026-06-01",
        window_end="2026-06-08",
        idempotency_key="m_drift_cmp",
        inject=golden_actual_drift_inject(),
    )
    report = fb6.get_report(run.run_id)
    checks["drift_critical"] = report.overall_severity == "CRITICAL"

    promo7, cand7, reg7, val7, _ = make_promotion_env(tmp / "m_skip")
    cand7_obj, _, validation_id = seed_promoted_registry(cand7, reg7, val7)
    try:
        promo7.submit_request(
            strategy_code=STRATEGY_CODE,
            candidate_id=cand7_obj.candidate_id,
            validation_id=validation_id,
            strategy_version=REGISTRY_VERSION,
            to_environment="LIVE",
            idempotency_key="m_skip_live",
            from_environment="SHADOW",
        )
        checks["shadow_to_live_rejected"] = False
    except PromotionError:
        checks["shadow_to_live_rejected"] = True

    return checks


def run_failure_inject_matrix_or_raise(tmp: Path) -> None:
    checks = run_failure_inject_matrix(tmp)
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise AssertionError(f"inject matrix failed: {failed}")


__all__ = ["run_failure_inject_matrix", "run_failure_inject_matrix_or_raise"]
