"""Phase 8G：Strategy Governance & Auto Guardrails 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.strategy_guardrails.decision import new_decision
from app.services.strategy_guardrails.protocol import ENGINE_VERSION
from app.services.strategy_guardrails.runner import (
    GuardrailDecisionError,
    StrategyGuardrailsError,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strategy_guardrails_golden.golden import (  # noqa: E402
    STRATEGY_CODE,
    golden_performance_critical_guardrail_inject,
    golden_recon_emergency_guardrail_inject,
    golden_risk_pause_guardrail_inject,
    golden_slippage_critical_guardrail_inject,
    make_guardrails_env,
    seed_guardrails_baseline,
)


def test_engine_version():
    assert ENGINE_VERSION == "qd_strategy_guardrails@1"


def test_slippage_critical_throttle_lifecycle_live(tmp_path):
    gr, mon, fb, promo, cand, reg, val, _s, gov = make_guardrails_env(tmp_path / "slip")
    seed_guardrails_baseline(mon, fb, promo, cand, reg, val, idempotency_key="slip_fb")
    result = gr.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_slippage_critical_guardrail_inject(),
        session_id="g1",
    )
    assert "THROTTLE" in result.actions_applied
    rt = gr.get_runtime_state(STRATEGY_CODE)
    assert rt.runtime_status == "THROTTLED"
    assert rt.lifecycle_phase == "LIVE"
    assert gov._runtime_throttle_log


def test_recon_emergency_safety_stop_no_flatten(tmp_path):
    gr, mon, fb, promo, cand, reg, val, safety, _gov = make_guardrails_env(tmp_path / "recon")
    seed_guardrails_baseline(mon, fb, promo, cand, reg, val, idempotency_key="recon_fb")
    gr.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_recon_emergency_guardrail_inject(),
        session_id="g2",
    )
    rt = gr.get_runtime_state(STRATEGY_CODE)
    assert rt.runtime_status == "STOPPED"
    assert safety.halts


def test_performance_critical_review_no_auto_stop(tmp_path):
    gr, mon, fb, promo, cand, reg, val, safety, _gov = make_guardrails_env(tmp_path / "perf")
    seed_guardrails_baseline(mon, fb, promo, cand, reg, val, idempotency_key="perf_fb")
    result = gr.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_performance_critical_guardrail_inject(),
        session_id="g3",
    )
    assert "STOP" not in result.actions_applied
    assert "ROLLBACK" not in result.actions_applied
    assert not safety.halts
    incs = gr.list_incidents(STRATEGY_CODE)
    assert incs
    assert any(i.status == "REVIEW_REQUIRED" for i in incs)


def test_auto_pause_ok_stop_without_approval_rejected(tmp_path):
    gr, mon, fb, promo, cand, reg, val, _s, _gov = make_guardrails_env(tmp_path / "pause")
    seed_guardrails_baseline(mon, fb, promo, cand, reg, val, idempotency_key="pause_fb")
    res = gr.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_risk_pause_guardrail_inject(),
        session_id="g4",
    )
    assert "PAUSE" in res.actions_applied
    assert gr.get_runtime_state(STRATEGY_CODE).runtime_status == "PAUSED"

    pending = new_decision(
        strategy_code=STRATEGY_CODE,
        decision_type="STOP",
        reason="manual stop",
        status="PENDING",
    )
    gr.submit_decision(pending)
    with pytest.raises(GuardrailDecisionError):
        gr.execute_approved_decision(pending.decision_id)

    rb = new_decision(
        strategy_code=STRATEGY_CODE,
        decision_type="ROLLBACK",
        to_version="v0",
        status="PENDING",
    )
    gr.submit_decision(rb)
    with pytest.raises(GuardrailDecisionError):
        gr.execute_approved_decision(rb.decision_id)


def test_resume_blocked_until_recovery(tmp_path):
    gr, mon, fb, promo, cand, reg, val, _s, _gov = make_guardrails_env(tmp_path / "resume")
    seed_guardrails_baseline(mon, fb, promo, cand, reg, val, idempotency_key="resume_fb")
    gr.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_risk_pause_guardrail_inject(),
        session_id="g5",
    )
    with pytest.raises(StrategyGuardrailsError):
        gr.resume(STRATEGY_CODE, operator="op")
    gr.resume(
        STRATEGY_CODE,
        operator="op",
        inject={"guardrails": {"recovery_healthy": True}},
    )
    assert gr.get_runtime_state(STRATEGY_CODE).runtime_status == "ACTIVE"


def test_rollback_record_lineage(tmp_path):
    gr, mon, fb, promo, cand, reg, val, _s, _gov = make_guardrails_env(tmp_path / "rb")
    seed_guardrails_baseline(mon, fb, promo, cand, reg, val, idempotency_key="rb_fb")
    rec = gr.rollback(
        STRATEGY_CODE,
        "v_prev",
        operator="op",
        from_version="v_live",
    )
    assert rec.from_version == "v_live"
    assert rec.to_version == "v_prev"
    rows = gr._registry.list_guardrail_rollback_records(STRATEGY_CODE)
    assert rows


def test_capital_not_reallocated_on_pause(tmp_path):
    gr, mon, fb, promo, cand, reg, val, _s, gov = make_guardrails_env(tmp_path / "cap")
    seed_guardrails_baseline(mon, fb, promo, cand, reg, val, idempotency_key="cap_fb")
    gr.evaluate_from_monitoring(
        STRATEGY_CODE,
        inject=golden_risk_pause_guardrail_inject(),
        session_id="g6",
    )
    assert gov._runtime_pause_log
    assert all("target_strategy" not in x for x in gov._runtime_pause_log)


def test_no_forbidden_tokens_in_package():
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "strategy_guardrails"
    )
    forbidden = ("submit_order", "mutate_version", "promote")
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        text = ast.dump(tree)
        for token in forbidden:
            assert token not in text
