#!/usr/bin/env python3
"""Phase 8F 验收：Strategy Monitoring（Fake inject / LocalJson）。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase8f_strategy_monitoring.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "research_data"))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")


def main() -> int:
    from app.services.strategy_monitoring.protocol import ENGINE_VERSION
    from strategy_monitoring_golden.golden import (
        STRATEGY_CODE,
        golden_healthy_monitor_inject,
        golden_market_data_critical_inject,
        golden_risk_recon_critical_inject,
        make_monitoring_env,
        seed_feedback_comparison,
    )

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase8f_"))
    checks: dict[str, bool] = {}

    checks["engine_version"] = ENGINE_VERSION == "qd_strategy_monitoring@1"

    mon, fb, promo, cand_svc, reg_svc, val_svc, _ = make_monitoring_env(tmp)
    seed_feedback_comparison(fb, promo, cand_svc, reg_svc, val_svc)

    health = mon.collect_and_evaluate(
        STRATEGY_CODE, inject=golden_healthy_monitor_inject(), session_id="verify"
    )
    checks["fake_inject_not_unknown"] = health.overall != "UNKNOWN"
    checks["metrics_present"] = len(mon.list_metrics(STRATEGY_CODE)) >= 5

    crit = mon.collect_and_evaluate(
        STRATEGY_CODE, inject=golden_risk_recon_critical_inject(), session_id="verify2"
    )
    checks["risk_recon_overall_critical"] = crit.overall == "CRITICAL"
    checks["alerts_created"] = bool(mon.list_alerts(STRATEGY_CODE))
    checks["governance_events"] = bool(mon.list_governance_events(STRATEGY_CODE))

    inj = golden_healthy_monitor_inject()
    inj["reconciliation"] = {"critical_finding_count": 2, "severity": "CRITICAL"}
    before_nfy = len(mon.list_notifications(STRATEGY_CODE))
    mon.collect_and_evaluate(STRATEGY_CODE, inject=inj, session_id="dedupe")
    mon.collect_and_evaluate(STRATEGY_CODE, inject=inj, session_id="dedupe")
    recon = [a for a in mon.list_alerts(STRATEGY_CODE) if a.rule_id == "recon_open_findings"]
    checks["alert_dedupe_one"] = len(recon) == 1 and recon[0].occurrence_count >= 2
    checks["cooldown_no_spam"] = len(mon.list_notifications(STRATEGY_CODE)) == before_nfy

    md_crit = mon.collect_and_evaluate(
        STRATEGY_CODE, inject=golden_market_data_critical_inject(), session_id="worst"
    )
    checks["worst_not_average"] = md_crit.overall == "CRITICAL"

    dash = mon.get_dashboard(STRATEGY_CODE)
    checks["dashboard_complete"] = bool(
        dash.health and dash.performance and dash.risk is not None
    )

    ok = all(checks.values())
    print(json.dumps({"phase": "8f", "ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
