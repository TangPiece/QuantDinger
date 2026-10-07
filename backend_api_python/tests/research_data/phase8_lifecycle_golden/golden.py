"""Phase 8I: single tmp env Research → Production → Research lifecycle chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.production_research_feedback.protocol import ResearchFeedbackQuery
from app.services.production_research_feedback.runner import ProductionResearchFeedbackService
from app.services.research_data.data_query import DataQuery

from production_research_feedback_golden.golden import golden_production_feedback_inject
from promotion_pipeline_golden.golden import seed_promoted_registry
from strategy_candidate_golden.golden import REGISTRY_VERSION
from strategy_guardrails_golden.golden import (
    STRATEGY_CODE,
    golden_risk_pause_guardrail_inject,
    make_guardrails_env,
)
from performance_feedback_golden.golden import (
    golden_actual_drift_inject,
    golden_baseline_metrics_inject,
)
from strategy_monitoring_golden.golden import golden_risk_recon_critical_inject
from validation_gate_golden.golden import golden_pass_inject

from phase8_hardening.fsm_checks import assert_runtime_paused_not_lifecycle_retired
from phase8_hardening.lineage_checks import (
    assert_experiment_parent_lineage,
    forward_lineage_chain,
    resolve_failure_case_back,
)


def make_lifecycle_env(
    tmp: Path,
) -> tuple[
    ProductionResearchFeedbackService,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    DataQuery,
]:
    gr, mon, fb, promo, cand, reg, val, safety, gov = make_guardrails_env(tmp)
    store = mon._store
    registry = gr._registry
    dq = DataQuery(store, registry)
    # Inject-only 8H path (lineage in golden_production_feedback_inject); avoids bridge collectors in E2E.
    prf = ProductionResearchFeedbackService(store, registry, data_query=dq)
    art = tmp / "artifacts"
    prf._writer._artifacts.root = art
    return prf, gr, mon, fb, promo, cand, reg, val, dq


def run_lifecycle_e2e_chain(tmp: Path) -> dict[str, Any]:
    prf, gr, mon, fb, promo, cand_svc, reg, val_svc, dq = make_lifecycle_env(tmp)

    cand, _ver, validation_id = seed_promoted_registry(cand_svc, reg, val_svc)
    val_run = val_svc.run(cand.candidate_id, inject=golden_pass_inject(), operator="e2e")
    assert val_run.status == "PASSED"

    req = promo.submit_request(
        strategy_code=STRATEGY_CODE,
        candidate_id=cand.candidate_id,
        validation_id=validation_id,
        strategy_version=REGISTRY_VERSION,
        to_environment="SHADOW",
        idempotency_key="e2e_shadow",
    )
    from promotion_pipeline_golden.golden import golden_promotion_metrics_inject

    run = promo.execute(req.request_id, inject=golden_promotion_metrics_inject())
    assert run.status == "COMPLETED" and run.to_environment == "SHADOW"
    pipeline_run_id = run.pipeline_run_id

    base = fb.freeze_baseline_from_promotion(
        pipeline_run_id, metrics_inject=golden_baseline_metrics_inject()
    )
    baseline_id = base.baseline_id
    cmp_run = fb.run_comparison(
        baseline_id=baseline_id,
        actual_source="SHADOW",
        window_start="2026-05-01",
        window_end="2026-05-08",
        idempotency_key="e2e_cmp",
        inject=golden_actual_drift_inject(),
    )
    comparison_run_id = cmp_run.run_id

    health = mon.collect_and_evaluate(
        STRATEGY_CODE, inject=golden_risk_recon_critical_inject(), session_id="e2e_mon"
    )
    assert health.overall == "CRITICAL"
    alerts = mon.list_alerts(STRATEGY_CODE)
    alert_id = alerts[0].alert_id if alerts else ""

    gr_result = gr.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_risk_pause_guardrail_inject(),
        session_id="e2e_gr",
    )
    assert "PAUSE" in gr_result.actions_applied
    runtime = gr.get_runtime_state(STRATEGY_CODE)
    assert_runtime_paused_not_lifecycle_retired(
        runtime_status=runtime.runtime_status,
        lifecycle_phase=runtime.lifecycle_phase,
    )
    incs = gr.list_incidents(STRATEGY_CODE)
    incident_id = incs[0].incident_id if incs else ""

    inj = golden_production_feedback_inject()
    pf_section = dict(inj.get("production_feedback") or {})
    lineage = dict(pf_section.get("lineage") or {})
    lineage.setdefault("comparison_run_id", comparison_run_id)
    lineage.setdefault("incident_id", incident_id)
    lineage.setdefault("strategy_version", REGISTRY_VERSION)
    pf_section["lineage"] = lineage
    inj = {"production_feedback": pf_section}

    ds = prf.build_dataset(
        STRATEGY_CODE,
        "PERFORMANCE_FEEDBACK",
        "2025-05-01",
        "2025-06-01",
        inject=inj,
        session_id="e2e_prf",
    )
    snap = prf.build_reality_snapshot(
        STRATEGY_CODE,
        dataset_id=ds.dataset_id,
        inject=inj,
        session_id="e2e_prf",
    )
    case = prf.record_failure_case(
        STRATEGY_CODE,
        feedback_dataset_id=ds.dataset_id,
        inject=inj,
        summary="e2e lifecycle failure",
        session_id="e2e_prf",
    )
    hyp = prf.create_hypothesis(
        STRATEGY_CODE,
        "e2e hypothesis",
        failure_case_ids=[case.case_id],
        feedback_dataset_id=ds.dataset_id,
        session_id="e2e_prf",
    )
    link = prf.link_experiment(
        "exp_e2e_8i",
        strategy_code=STRATEGY_CODE,
        feedback_dataset_id=ds.dataset_id,
        failure_case_ids=[case.case_id],
        incident_ids=[case.incident_id or incident_id],
        hypothesis_id=hyp.hypothesis_id,
    )
    stored_link = prf._registry.get_feedback_experiment_link(link.link_id)
    assert_experiment_parent_lineage(stored_link, dataset_id=ds.dataset_id, case_ids=[case.case_id])

    rows = dq.production_feedback(
        ResearchFeedbackQuery(strategy_code=STRATEGY_CODE, reality_kind="ACTUAL")
    )
    assert any(r.record_kind == "DATASET" for r in rows)

    back = resolve_failure_case_back(
        case=case, registry=prf._registry, strategy_code=STRATEGY_CODE
    )
    assert back["strategy_code"] == STRATEGY_CODE
    assert back["feedback_dataset_id"] == ds.dataset_id

    artifacts = {
        "pipeline_run_id": pipeline_run_id,
        "baseline_id": baseline_id,
        "comparison_run_id": comparison_run_id,
        "alert_id": alert_id,
        "incident_id": incident_id or case.incident_id,
        "dataset_id": ds.dataset_id,
        "snapshot_id": snap.snapshot_id,
        "case_id": case.case_id,
        "hypothesis_id": hyp.hypothesis_id,
        "experiment_link_id": link.link_id,
        "runtime_status": runtime.runtime_status,
        "lifecycle_phase": runtime.lifecycle_phase,
    }
    chain = forward_lineage_chain(artifacts)
    return {
        "artifacts": artifacts,
        "lineage_chain": chain,
        "dataquery_rows": len(rows),
        "runtime_separated": runtime.runtime_status == "PAUSED"
        and runtime.lifecycle_phase != "RETIRED",
    }


__all__ = ["make_lifecycle_env", "run_lifecycle_e2e_chain", "STRATEGY_CODE"]
