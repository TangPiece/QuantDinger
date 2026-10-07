#!/usr/bin/env python3
"""Phase 9F-9 — Model Platform E2E Acceptance & Hardening orchestrator。"""

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

PHASE9F_VERIFY_SCRIPTS = (
    "verify_phase9f_model_platform.py",
    "verify_phase9f4_qlib_adapter.py",
    "verify_phase9f5_model_artifact.py",
    "verify_phase9f6_model_evaluation.py",
    "verify_phase9f7_model_approval.py",
    "verify_phase9f8_model_reproducibility.py",
)


def _run_script(name: str) -> bool:
    script = ROOT / "scripts" / name
    env = {**os.environ, "QUANTDINGER_SKIP_APP_INIT": "1"}
    if "phase9f4" in name:
        env.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
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

    phase_ok = True
    for script in PHASE9F_VERIFY_SCRIPTS:
        ok = _run_script(script)
        checks[script.replace(".py", "")] = ok
        phase_ok = phase_ok and ok
    checks["phase9f1_to_8_verifies"] = phase_ok

    checks["phase9e_regression"] = _run_script("verify_phase9e_factor_library.py")

    sys.path.insert(0, str(ROOT / "scripts"))
    from scan_phase9f_plane_isolation import run_scan

    scan = run_scan()
    checks["plane_isolation_scan"] = bool(scan.get("clean"))

    tmp = Path(tempfile.mkdtemp(prefix="qd_phase9f9_"))

    from phase9f_hardening.fsm_checks import run_fsm_checks

    fsm = run_fsm_checks(tmp / "fsm")
    checks["fsm_hardening"] = all(fsm.values())

    from phase9f_hardening.immutability_checks import run_immutability_battery

    imm = run_immutability_battery(tmp / "imm")
    checks["immutability_battery"] = all(imm.values())

    from phase9f_hardening.inject_matrix import run_inject_matrix

    inj = run_inject_matrix(tmp / "inj")
    checks["inject_matrix"] = all(inj.values())

    from phase9f_hardening.lineage_checks import run_lineage_checks

    lin = run_lineage_checks(tmp / "lin")
    checks["lineage_checks"] = all(lin.values())

    from phase9f_hardening.concurrency_checks import run_concurrency_checks

    conc = run_concurrency_checks(tmp / "conc")
    checks["concurrency_single_active"] = all(conc.values())

    from phase9f_lifecycle_golden.golden import run_model_lifecycle_e2e_chain

    e2e = run_model_lifecycle_e2e_chain(tmp / "e2e")
    checks["e2e_lifecycle_chain"] = bool(e2e.get("ok"))

    # Done criteria rollup
    checks["done_lifecycle"] = checks["e2e_lifecycle_chain"]
    checks["done_binding"] = checks["e2e_lifecycle_chain"]
    checks["done_gates"] = checks["fsm_hardening"] and checks["inject_matrix"]
    checks["done_traceability"] = checks["lineage_checks"]
    checks["done_immutability"] = checks["immutability_battery"]
    checks["done_reproduce"] = checks["e2e_lifecycle_chain"]
    checks["done_fault_idempotency_concurrency"] = (
        checks["inject_matrix"] and checks["concurrency_single_active"]
    )
    checks["done_full_lineage"] = checks["lineage_checks"]

    failed = [k for k, ok in checks.items() if not ok]
    print(
        json.dumps(
            {
                "ok": not failed,
                "checks": checks,
                "failed": failed,
                "scan_violations": scan.get("violations") or [],
                "e2e": e2e,
            },
            indent=2,
            default=str,
        )
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
