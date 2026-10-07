"""Phase 8I — Architecture hardening + lifecycle E2E acceptance."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(SCRIPTS))

from phase8_hardening.fsm_checks import run_fsm_checks  # noqa: E402
from phase8_hardening.immutability_checks import run_immutability_battery  # noqa: E402
from phase8_hardening.inject_matrix import run_failure_inject_matrix  # noqa: E402
from phase8_lifecycle_golden.golden import run_lifecycle_e2e_chain  # noqa: E402


def test_plane_isolation_scan_clean():
    from scan_phase8_plane_isolation import run_scan

    summary = run_scan()
    assert summary["clean"], json.dumps(summary.get("violations", [])[:5], indent=2)


def test_fsm_and_runtime_lifecycle_invariant():
    result = run_fsm_checks()
    assert all(result.values())


def test_immutability_battery(tmp_path):
    checks = run_immutability_battery(tmp_path / "immut")
    assert all(checks.values()), checks


def test_failure_inject_matrix(tmp_path):
    checks = run_failure_inject_matrix(tmp_path / "inj")
    assert all(checks.values()), checks


def test_e2e_lifecycle_chain(tmp_path):
    out = run_lifecycle_e2e_chain(tmp_path / "e2e")
    assert out["dataquery_rows"] > 0
    assert out["runtime_separated"]
    assert len(out["lineage_chain"]) >= 6


def test_verify_script_smoke(tmp_path):
    """Lightweight: new checks only (full 8A–8H run via verify script in CI)."""
    py = ROOT / ".test_deps" / "py312" / "bin" / "python"
    if not py.is_file():
        pytest.skip("verify python env missing")
    env = {**dict(**{"QUANTDINGER_SKIP_APP_INIT": "1"}), **dict(__import__("os").environ)}
    proc = subprocess.run(
        [str(py), str(SCRIPTS / "scan_phase8_plane_isolation.py")],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
