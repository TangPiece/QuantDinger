#!/usr/bin/env python3
"""Phase 6I 验收：Paper / Shadow E2E。

用法::

    QUANTDINGER_SKIP_APP_INIT=1 .test_deps/py312/bin/python scripts/verify_phase6i_e2e.py
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
    pkg = ROOT / "app" / "services" / "e2e_service"
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
    from app.services.e2e_service.modes import assert_mode, E2EModeError
    from app.services.e2e_service.protocol import ReplayRequest
    from app.services.e2e_service.scenarios import ALL_SCENARIO_IDS
    from e2e_golden.golden import DATASET_HASH, STRATEGY_VERSION, make_env

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase6i_"))
    os.environ["QD_RESEARCH_CACHE_DIR"] = str(tmp / "cache")
    checks: dict[str, bool] = {}

    checks["ast_isolation"] = _domain_isolation()

    live_blocked = False
    try:
        assert_mode("LIVE")
    except E2EModeError:
        live_blocked = True
    checks["live_forbidden"] = live_blocked

    *_, e2e = make_env(tmp)
    suite = e2e.run_suite(mode="PAPER", salt="verify")
    checks["suite_all_ok"] = len(suite) == len(ALL_SCENARIO_IDS) and all(
        r.status == "OK" for r in suite
    )

    e2e.start_session(mode="SHADOW", salt="vsh")
    sh = e2e.run_scenario("E2E-001", mode="SHADOW", salt="vsh")
    checks["shadow_virtual"] = bool(sh.virtual_orders) and not sh.order_ids

    rep = e2e.replay(
        ReplayRequest(
            dataset_hash=DATASET_HASH,
            strategy_version=STRATEGY_VERSION,
            fixture_id="e2e_fixture_v1",
            scenario_id="E2E-001",
        )
    )
    checks["replay_ok"] = rep.ok and not rep.drift_detected

    run_id = suite[0].run_id if suite else ""
    score = e2e.consistency_score(run_id) if run_id else None
    checks["consistency_score"] = bool(score and score.overall > 0.5)

    failed = [k for k, v in checks.items() if not v]
    print(json.dumps({"ok": not failed, "checks": checks, "failed": failed}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
