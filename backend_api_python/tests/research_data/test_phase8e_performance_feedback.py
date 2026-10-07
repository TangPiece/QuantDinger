"""Phase 8E：Live Performance Feedback 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.live_performance_feedback.protocol import ENGINE_VERSION
from app.services.live_performance_feedback.runner import (
    LivePerformanceFeedbackService,
    PerformanceFeedbackError,
)
from app.services.strategy_registry.runner import StrategyRegistryService

sys.path.insert(0, str(Path(__file__).resolve().parent))
from performance_feedback_golden.golden import (  # noqa: E402
    REGISTRY_VERSION,
    STRATEGY_CODE,
    golden_actual_drift_inject,
    golden_baseline_metrics_inject,
    make_feedback_env,
    seed_completed_promotion,
)


def test_engine_version():
    assert ENGINE_VERSION == "qd_live_performance_feedback@1"


def test_freeze_baseline_from_promotion(tmp_path):
    fb, promo, cand_svc, reg_svc, val_svc, _ = make_feedback_env(tmp_path / "freeze")
    pid = seed_completed_promotion(promo, cand_svc, reg_svc, val_svc)
    base = fb.freeze_baseline_from_promotion(
        pid, metrics_inject=golden_baseline_metrics_inject()
    )
    assert base.immutable is True
    assert base.pipeline_run_id == pid
    assert base.metrics_snapshot.sharpe == 1.5
    again = fb.freeze_baseline_from_promotion(pid)
    assert again.baseline_id == base.baseline_id


def test_baseline_immutable_rejects_metrics_change(tmp_path):
    fb, promo, cand_svc, reg_svc, val_svc, _ = make_feedback_env(tmp_path / "immut")
    pid = seed_completed_promotion(promo, cand_svc, reg_svc, val_svc, idempotency_key="immut_1")
    fb.freeze_baseline_from_promotion(pid, metrics_inject=golden_baseline_metrics_inject())
    with pytest.raises(PerformanceFeedbackError, match="immutable"):
        fb.freeze_baseline_from_promotion(
            pid,
            metrics_inject={**golden_baseline_metrics_inject(), "sharpe": 9.9},
        )


def test_comparison_report_and_drift(tmp_path):
    fb, promo, cand_svc, reg_svc, val_svc, _ = make_feedback_env(tmp_path / "cmp")
    pid = seed_completed_promotion(promo, cand_svc, reg_svc, val_svc, idempotency_key="cmp_1")
    base = fb.freeze_baseline_from_promotion(
        pid, metrics_inject=golden_baseline_metrics_inject()
    )
    run = fb.run_comparison(
        baseline_id=base.baseline_id,
        actual_source="SHADOW",
        window_start="2026-01-01",
        window_end="2026-01-08",
        idempotency_key="win_1",
        inject=golden_actual_drift_inject(),
    )
    assert run.status == "PUBLISHED"
    report = fb.get_report(run.run_id)
    assert report.findings
    assert report.overall_severity in ("WARNING", "CRITICAL")
    assert report.attribution.cost_bps != 0.0 or report.attribution.slippage_bps != 0.0
    types = {f.drift_type for f in report.findings}
    assert "SIGNAL_DRIFT" in types or "RISK_DRIFT" in types


def test_comparison_idempotent(tmp_path):
    fb, promo, cand_svc, reg_svc, val_svc, _ = make_feedback_env(tmp_path / "idem")
    pid = seed_completed_promotion(promo, cand_svc, reg_svc, val_svc, idempotency_key="idem_2")
    base = fb.freeze_baseline_from_promotion(
        pid, metrics_inject=golden_baseline_metrics_inject()
    )
    inj = golden_actual_drift_inject()
    r1 = fb.run_comparison(
        baseline_id=base.baseline_id,
        actual_source="SHADOW",
        window_start="2026-02-01",
        window_end="2026-02-08",
        idempotency_key="idem_cmp",
        inject=inj,
    )
    r2 = fb.run_comparison(
        baseline_id=base.baseline_id,
        actual_source="SHADOW",
        window_start="2026-02-01",
        window_end="2026-02-08",
        idempotency_key="idem_cmp",
        inject=inj,
    )
    assert r1.run_id == r2.run_id
    assert r1.status == "PUBLISHED"


def test_latest_drift_scalars(tmp_path):
    fb, promo, cand_svc, reg_svc, val_svc, _ = make_feedback_env(tmp_path / "scalar")
    pid = seed_completed_promotion(promo, cand_svc, reg_svc, val_svc, idempotency_key="scalar_1")
    base = fb.freeze_baseline_from_promotion(
        pid, metrics_inject=golden_baseline_metrics_inject()
    )
    fb.run_comparison(
        baseline_id=base.baseline_id,
        actual_source="SHADOW",
        window_start="2026-03-01",
        window_end="2026-03-08",
        idempotency_key="scalar_cmp",
        inject=golden_actual_drift_inject(),
    )
    scalars = fb.latest_drift_scalars(STRATEGY_CODE)
    assert scalars.get("shadow_drift", 0) > 0.1


def test_does_not_mutate_strategy_version(tmp_path):
    fb, promo, cand_svc, reg_svc, val_svc, _ = make_feedback_env(tmp_path / "lineage")
    pid = seed_completed_promotion(promo, cand_svc, reg_svc, val_svc, idempotency_key="lin_1")
    reg_svc: StrategyRegistryService = reg_svc
    ver_before = reg_svc.get_version(STRATEGY_CODE, REGISTRY_VERSION)
    base = fb.freeze_baseline_from_promotion(
        pid, metrics_inject=golden_baseline_metrics_inject()
    )
    fb.run_comparison(
        baseline_id=base.baseline_id,
        actual_source="SHADOW",
        window_start="2026-04-01",
        window_end="2026-04-08",
        idempotency_key="lin_cmp",
        inject=golden_actual_drift_inject(),
    )
    ver_after = reg_svc.get_version(STRATEGY_CODE, ver_before.strategy_version)
    assert ver_after.content_hash == ver_before.content_hash


def test_no_oms_in_package():
    root = Path(__file__).resolve().parents[2] / "app" / "services" / "live_performance_feedback"
    forbidden = ("submit_order", "stop_live", "demote", "mutate_version")
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        text = ast.dump(tree)
        for token in forbidden:
            assert token not in text
