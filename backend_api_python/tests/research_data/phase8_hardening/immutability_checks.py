"""Immutable overwrite battery (Registry / Candidate / Baseline / Snapshot / Rollback)."""

from __future__ import annotations

from pathlib import Path

from app.services.live_performance_feedback.runner import PerformanceFeedbackError
from app.services.production_research_feedback.runner import ProductionResearchFeedbackError
from app.services.strategy_candidate.runner import LineageImmutableError
from app.services.strategy_registry.runner import VersionImmutableError

from performance_feedback_golden.golden import (
    golden_baseline_metrics_inject,
    make_feedback_env,
    seed_completed_promotion,
)
from production_research_feedback_golden.golden import (
    golden_production_feedback_inject,
    make_feedback_env as make_prf_env,
)
from strategy_candidate_golden.golden import (
    BACKTEST_HASH,
    CAND_VERSION,
    EXPERIMENT_ID,
    STRATEGY_CODE,
    STRATEGY_HASH,
    make_candidate_env,
)
from strategy_registry_golden.golden import (
    BUNDLE_HASH,
    STRATEGY_CODE as REG_STRATEGY_CODE,
    STRATEGY_VERSION,
    make_registry_env,
)
from strategy_guardrails_golden.golden import STRATEGY_CODE as GR_STRATEGY
from strategy_guardrails_golden.golden import make_guardrails_env, seed_guardrails_baseline


def run_immutability_battery(tmp: Path) -> dict[str, bool]:
    checks: dict[str, bool] = {}

    reg_svc, _, _ = make_registry_env(tmp / "reg_immut")
    reg_svc.register_version_from_bundle(BUNDLE_HASH, strategy_version_label=STRATEGY_VERSION)
    try:
        reg_svc.set_policy_bindings(REG_STRATEGY_CODE, STRATEGY_VERSION, risk_ref="other@v2")
        checks["registry_version"] = False
    except VersionImmutableError:
        checks["registry_version"] = True

    cand_svc, _, _ = make_candidate_env(tmp / "cand_immut")
    cand_svc.create_from_research(
        STRATEGY_CODE,
        candidate_version=CAND_VERSION,
        experiment_id=EXPERIMENT_ID,
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
    )
    try:
        cand_svc.create_from_research(
            STRATEGY_CODE,
            candidate_version=CAND_VERSION,
            experiment_id=EXPERIMENT_ID,
            backtest_hash=BACKTEST_HASH,
            strategy_hash=STRATEGY_HASH,
            dataset_hash="mutated_dh",
        )
        checks["candidate_lineage"] = False
    except LineageImmutableError:
        checks["candidate_lineage"] = True

    fb, promo, cand_svc2, reg_svc2, val_svc, _ = make_feedback_env(tmp / "base_immut")
    pid = seed_completed_promotion(
        promo, cand_svc2, reg_svc2, val_svc, idempotency_key="immut_base"
    )
    fb.freeze_baseline_from_promotion(pid, metrics_inject=golden_baseline_metrics_inject())
    try:
        fb.freeze_baseline_from_promotion(
            pid,
            metrics_inject={**golden_baseline_metrics_inject(), "sharpe": 99.0},
        )
        checks["performance_baseline"] = False
    except PerformanceFeedbackError:
        checks["performance_baseline"] = True

    prf, _reg, _dq = make_prf_env(tmp / "snap_immut")
    inj = golden_production_feedback_inject()
    first = prf.build_reality_snapshot(GR_STRATEGY, inject=inj, session_id="immut")
    bad = {
        "production_feedback": {
            **inj["production_feedback"],
            "metrics": {"return_total": 0.99},
        }
    }
    try:
        prf.build_reality_snapshot(GR_STRATEGY, inject=bad, session_id="immut")
        checks["reality_snapshot"] = False
    except ProductionResearchFeedbackError:
        checks["reality_snapshot"] = True
    else:
        checks["reality_snapshot"] = False

    gr, mon, fb2, promo2, cand3, reg3, val3, _s, _gov = make_guardrails_env(tmp / "rb_immut")
    seed_guardrails_baseline(mon, fb2, promo2, cand3, reg3, val3, idempotency_key="rb_immut")
    rec = gr.rollback(GR_STRATEGY, "v_prev", operator="immut", from_version="v_live")
    stored = gr._registry.list_guardrail_rollback_records(GR_STRATEGY)
    match = [r for r in stored if r.rollback_id == rec.rollback_id]
    checks["rollback_record_pinned"] = bool(match) and match[0].to_version == "v_prev"
    assert first.snapshot_id

    return checks


def run_immutability_battery_or_raise(tmp: Path) -> None:
    checks = run_immutability_battery(tmp)
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise AssertionError(f"immutability battery failed: {failed}")


__all__ = ["run_immutability_battery", "run_immutability_battery_or_raise"]
