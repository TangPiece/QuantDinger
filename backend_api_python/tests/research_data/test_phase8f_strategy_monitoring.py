"""Phase 8F：Strategy Monitoring & Alerting 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.strategy_monitoring.protocol import ENGINE_VERSION
from app.services.strategy_monitoring.runner import StrategyMonitoringService

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strategy_monitoring_golden.golden import (  # noqa: E402
    STRATEGY_CODE,
    golden_healthy_monitor_inject,
    golden_market_data_critical_inject,
    golden_risk_recon_critical_inject,
    make_monitoring_env,
    seed_feedback_comparison,
)


def test_engine_version():
    assert ENGINE_VERSION == "qd_strategy_monitoring@1"


def test_fake_inject_health_not_unknown(tmp_path):
    mon, fb, promo, cand_svc, reg_svc, val_svc, _ = make_monitoring_env(
        tmp_path / "healthy"
    )
    seed_feedback_comparison(fb, promo, cand_svc, reg_svc, val_svc)
    health = mon.collect_and_evaluate(
        STRATEGY_CODE, inject=golden_healthy_monitor_inject(), session_id="s1"
    )
    assert health.overall != "UNKNOWN"
    metrics = mon.list_metrics(STRATEGY_CODE)
    assert len(metrics) >= 5
    cats = {m.category for m in metrics}
    assert "PERFORMANCE" in cats and "RISK" in cats and "MARKET_DATA" in cats


def test_risk_recon_critical_alert_governance(tmp_path):
    mon, fb, promo, cand_svc, reg_svc, val_svc, _ = make_monitoring_env(
        tmp_path / "critical"
    )
    seed_feedback_comparison(
        fb, promo, cand_svc, reg_svc, val_svc, idempotency_key="crit_fb"
    )
    health = mon.collect_and_evaluate(
        STRATEGY_CODE, inject=golden_risk_recon_critical_inject(), session_id="s2"
    )
    assert health.overall == "CRITICAL"
    alerts = mon.list_alerts(STRATEGY_CODE)
    assert alerts
    assert any(a.severity in ("CRITICAL", "EMERGENCY") for a in alerts)
    gov = mon.list_governance_events(STRATEGY_CODE)
    assert gov
    assert all(e.event_type == "REVIEW_REQUIRED" for e in gov)


def test_alert_dedupe_and_cooldown(tmp_path):
    mon, fb, promo, cand_svc, reg_svc, val_svc, _ = make_monitoring_env(
        tmp_path / "dedupe"
    )
    seed_feedback_comparison(
        fb, promo, cand_svc, reg_svc, val_svc, idempotency_key="dedupe_fb"
    )
    inj = golden_healthy_monitor_inject()
    inj["reconciliation"] = {"critical_finding_count": 2, "severity": "CRITICAL"}
    mon.collect_and_evaluate(STRATEGY_CODE, inject=inj, session_id="s3")
    mon.collect_and_evaluate(STRATEGY_CODE, inject=inj, session_id="s3")
    mon.collect_and_evaluate(STRATEGY_CODE, inject=inj, session_id="s3")
    alerts = mon.list_alerts(STRATEGY_CODE)
    recon_alerts = [a for a in alerts if a.rule_id == "recon_open_findings"]
    assert len(recon_alerts) == 1
    assert recon_alerts[0].occurrence_count >= 3
    notifications = mon.list_notifications(STRATEGY_CODE)
    assert len(notifications) == 1


def test_worst_priority_not_average(tmp_path):
    mon, fb, promo, cand_svc, reg_svc, val_svc, _ = make_monitoring_env(
        tmp_path / "worst"
    )
    seed_feedback_comparison(
        fb, promo, cand_svc, reg_svc, val_svc, idempotency_key="worst_fb"
    )
    health = mon.collect_and_evaluate(
        STRATEGY_CODE, inject=golden_market_data_critical_inject(), session_id="s4"
    )
    assert health.overall == "CRITICAL"
    perf = mon.get_performance(STRATEGY_CODE)
    assert perf.get("shadow_drift", 99) < 0.08


def test_dashboard_snapshot(tmp_path):
    mon, fb, promo, cand_svc, reg_svc, val_svc, _ = make_monitoring_env(
        tmp_path / "dash"
    )
    seed_feedback_comparison(
        fb, promo, cand_svc, reg_svc, val_svc, idempotency_key="dash_fb"
    )
    mon.collect_and_evaluate(
        STRATEGY_CODE, inject=golden_healthy_monitor_inject(), session_id="s5"
    )
    dash = mon.get_dashboard(STRATEGY_CODE)
    assert dash.health.strategy_code == STRATEGY_CODE
    assert dash.performance
    assert dash.risk is not None
    assert dash.execution is not None
    assert dash.drift is not None
    assert dash.reconciliation is not None


def test_alert_lifecycle(tmp_path):
    mon, fb, promo, cand_svc, reg_svc, val_svc, _ = make_monitoring_env(
        tmp_path / "fsm"
    )
    seed_feedback_comparison(
        fb, promo, cand_svc, reg_svc, val_svc, idempotency_key="fsm_fb"
    )
    mon.collect_and_evaluate(
        STRATEGY_CODE, inject=golden_risk_recon_critical_inject(), session_id="s6"
    )
    alert = mon.list_alerts(STRATEGY_CODE)[0]
    ack = mon.ack_alert(alert.alert_id)
    assert ack.status == "ACKNOWLEDGED"
    inv = mon.investigate_alert(alert.alert_id)
    assert inv.status == "INVESTIGATING"
    res = mon.resolve_alert(alert.alert_id)
    assert res.status == "RESOLVED"


def test_no_oms_in_package():
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "strategy_monitoring"
    )
    forbidden = ("submit_order", "stop_live", "demote", "mutate_version")
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        text = ast.dump(tree)
        for token in forbidden:
            assert token not in text
