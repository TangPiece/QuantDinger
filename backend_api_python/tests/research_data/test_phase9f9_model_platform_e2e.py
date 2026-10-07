"""Phase 9F-9：E2E Acceptance & Hardening。"""

from __future__ import annotations

from pathlib import Path

from app.services.research_data.model_platform.runner import ModelPlatformService
from phase9f_hardening.concurrency_checks import run_concurrency_checks
from phase9f_hardening.fsm_checks import run_fsm_checks
from phase9f_hardening.immutability_checks import run_immutability_battery
from phase9f_hardening.inject_matrix import run_inject_matrix
from phase9f_hardening.lineage_checks import run_lineage_checks
from phase9f_lifecycle_golden.golden import run_model_lifecycle_e2e_chain


def test_no_strategy_live_on_platform():
    assert not hasattr(ModelPlatformService, "auto_live")
    assert not hasattr(ModelPlatformService, "promote_strategy")
    assert hasattr(ModelPlatformService, "get_full_lineage")


def test_fsm_hardening(tmp_path: Path):
    assert all(run_fsm_checks(tmp_path / "fsm").values())


def test_immutability_battery(tmp_path: Path):
    assert all(run_immutability_battery(tmp_path / "imm").values())


def test_inject_matrix(tmp_path: Path):
    assert all(run_inject_matrix(tmp_path / "inj").values())


def test_lineage_checks(tmp_path: Path):
    assert all(run_lineage_checks(tmp_path / "lin").values())


def test_concurrency_single_active(tmp_path: Path):
    assert all(run_concurrency_checks(tmp_path / "conc").values())


def test_e2e_lifecycle_chain(tmp_path: Path):
    result = run_model_lifecycle_e2e_chain(tmp_path / "e2e")
    assert result["ok"] is True
    assert result["lineage_schema"] == "model_full_lineage@1"
