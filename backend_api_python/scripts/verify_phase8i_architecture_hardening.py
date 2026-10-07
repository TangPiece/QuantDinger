#!/usr/bin/env python3
"""Phase 8I — Architecture Hardening & E2E acceptance orchestrator."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "research_data"))

os.environ.setdefault("QUANTDINGER_SKIP_APP_INIT", "1")

PYTHON = os.environ.get("QUANTDINGER_VERIFY_PYTHON") or str(
    ROOT / ".test_deps" / "py312" / "bin" / "python"
)

PHASE8_VERIFY_SCRIPTS = (
    "verify_phase8a_strategy_registry.py",
    "verify_phase8b_strategy_candidate.py",
    "verify_phase8c_validation_gate.py",
    "verify_phase8d_promotion_pipeline.py",
    "verify_phase8e_performance_feedback.py",
    "verify_phase8f_strategy_monitoring.py",
    "verify_phase8g_strategy_guardrails.py",
    "verify_phase8h_production_research_feedback.py",
)


def _run_script(name: str) -> bool:
    script = ROOT / "scripts" / name
    env = {**os.environ, "QUANTDINGER_SKIP_APP_INIT": "1"}
    proc = subprocess.run(
        [PYTHON, str(script)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> int:
    checks: dict[str, bool] = {}

    phase8_ok = True
    for script in PHASE8_VERIFY_SCRIPTS:
        ok = _run_script(script)
        phase8_ok = phase8_ok and ok
    checks["phase8a_to_8h_verifies"] = phase8_ok

    sys.path.insert(0, str(ROOT / "scripts"))
    from scan_phase8_plane_isolation import run_scan

    scan = run_scan()
    checks["plane_isolation_scan"] = bool(scan.get("clean"))

    from phase8_hardening.fsm_checks import run_fsm_checks

    fsm = run_fsm_checks()
    checks["fsm_illegal_transitions_rejected"] = all(fsm.values())
    checks["runtime_lifecycle_separation"] = fsm.get("runtime_lifecycle_invariant", False)

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase8i_"))

    from phase8_hardening.immutability_checks import run_immutability_battery

    imm = run_immutability_battery(tmp / "immut")
    checks["immutability_battery"] = all(imm.values())

    from phase8_lifecycle_golden.golden import run_lifecycle_e2e_chain

    e2e = run_lifecycle_e2e_chain(tmp / "e2e")
    checks["e2e_lifecycle_chain"] = bool(
        e2e.get("dataquery_rows", 0) > 0 and e2e.get("runtime_separated")
    )
    checks["lineage_forward_and_back"] = len(e2e.get("lineage_chain") or []) >= 6

    from phase8_hardening.inject_matrix import run_failure_inject_matrix

    inj = run_failure_inject_matrix(tmp / "inj")
    checks["failure_inject_matrix"] = all(inj.values())

    checks["phase7e_regression"] = _run_script("verify_phase7e_gradual_scale.py")

    ok = all(checks.values())
    out = {"phase": "8i", "ok": ok, "checks": checks}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
