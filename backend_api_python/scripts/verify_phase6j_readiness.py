#!/usr/bin/env python3
"""Phase 6J 验收：Production Readiness checklist。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase6j_readiness.py
"""

from __future__ import annotations

import ast
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


def _domain_isolation() -> bool:
    pkg = ROOT / "app" / "services" / "production_readiness"
    forbidden = (
        "qlib",
        "strategy_v2",
        "live_trading",
        "pending_order",
        "DataSourceFactory",
    )
    for py in pkg.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    for frag in forbidden:
                        if frag in name:
                            return False
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for frag in forbidden:
                    if frag in mod:
                        return False
            if py.name == "modes.py":
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.strip().upper() == "LIVE":
                    return False
    return True


def main() -> int:
    from app.services.production_readiness.modes import ReadinessModeError, assert_mode
    from app.services.production_readiness.scenarios import ALL_SCENARIO_IDS
    from readiness_golden.golden import make_env

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase6j_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    checks: dict[str, bool] = {}

    checks["ast_isolation"] = _domain_isolation()

    live_blocked = False
    try:
        assert_mode("LIVE")
    except ReadinessModeError:
        live_blocked = True
    checks["live_forbidden"] = live_blocked

    *_, rdy = make_env(tmp)
    checklist = rdy.run_checklist(salt="verify")
    checks["production_ready"] = bool(checklist.production_ready)
    os.environ["PRODUCTION_READY"] = "true" if checklist.production_ready else "false"

    failed_scenarios = [
        c.scenario_id
        for c in checklist.checks
        if c.status != "OK"
    ]
    checks["all_scenarios"] = len(failed_scenarios) == 0 and len(
        checklist.checks
    ) == len(ALL_SCENARIO_IDS)

    rec = rdy.recover_on_start()
    checks["recover_no_resubmit"] = rec.resubmit_attempted is False

    fault = rdy.run_fault("FLT-DUP-EXEC")
    checks["fault_smoke"] = fault.status == "OK"

    failed = [k for k, v in checks.items() if not v]
    print(
        json.dumps(
            {
                "ok": not failed,
                "PRODUCTION_READY": checklist.production_ready,
                "checks": checks,
                "failed": failed,
            },
            indent=2,
        )
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
