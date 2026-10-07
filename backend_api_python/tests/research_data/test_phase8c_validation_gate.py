"""Phase 8C：Strategy Validation Gate 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.strategy_candidate.runner import CandidateError
from app.services.strategy_validation.protocol import ENGINE_VERSION
from app.services.strategy_validation.runner import ValidationGateService

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strategy_candidate_golden.golden import REGISTRY_VERSION  # noqa: E402
from validation_gate_golden.golden import (  # noqa: E402
    golden_pass_inject,
    golden_pit_leak_inject,
    make_validation_env,
    validated_candidate,
)


def test_engine_version():
    assert ENGINE_VERSION == "qd_strategy_validation@1"


def test_fake_inject_passed(tmp_path):
    val_svc, cand_svc, _ = make_validation_env(tmp_path / "pass")
    cand = validated_candidate(cand_svc)
    before_hash = cand.content_hash
    run = val_svc.run(cand.candidate_id, inject=golden_pass_inject(), operator="test")
    assert run.status == "PASSED"
    assert run.policy_id == "default_research_v1"
    assert run.policy_content_hash
    after = cand_svc.get(cand.candidate_id)
    assert after.content_hash == before_hash
    assert after.metadata.get("last_gate_status") == "PASSED"


def test_pit_leak_failed(tmp_path):
    val_svc, cand_svc, _ = make_validation_env(tmp_path / "pit")
    cand = validated_candidate(cand_svc)
    run = val_svc.run(cand.candidate_id, inject=golden_pit_leak_inject())
    assert run.status == "FAILED"


def test_idempotent_run_id(tmp_path):
    val_svc, cand_svc, _ = make_validation_env(tmp_path / "idem")
    cand = validated_candidate(cand_svc)
    inj = golden_pass_inject()
    r1 = val_svc.run(cand.candidate_id, inject=inj)
    r2 = val_svc.run(cand.candidate_id, inject=inj)
    assert r1.validation_id == r2.validation_id
    assert r1.status == r2.status == "PASSED"


def test_promote_requires_gate(tmp_path):
    val_svc, cand_svc, reg_svc = make_validation_env(tmp_path / "promote_gate")
    cand = validated_candidate(cand_svc)
    with pytest.raises(CandidateError):
        cand_svc.promote_to_registry(
            cand.candidate_id,
            target_strategy_version=REGISTRY_VERSION,
        )
    val_svc.run(cand.candidate_id, inject=golden_pass_inject())
    _, prom, ver = cand_svc.promote_to_registry(
        cand.candidate_id,
        target_strategy_version=REGISTRY_VERSION,
    )
    assert prom.to_state == "REGISTERED"
    assert ver.version_id


def test_promote_skip_gate_flag(tmp_path):
    val_svc, cand_svc, _ = make_validation_env(tmp_path / "promote_skip")
    cand = validated_candidate(cand_svc)
    _, prom, _ = cand_svc.promote_to_registry(
        cand.candidate_id,
        target_strategy_version=REGISTRY_VERSION,
        require_gate_passed=False,
    )
    assert prom.to_state == "REGISTERED"
    _ = val_svc


def test_list_policies_and_runs(tmp_path):
    val_svc, cand_svc, _ = make_validation_env(tmp_path / "list")
    cand = validated_candidate(cand_svc)
    val_svc.run(cand.candidate_id, inject=golden_pass_inject())
    policies = val_svc.list_policies()
    assert any(p.policy_id == "default_research_v1" for p in policies)
    runs = val_svc.list_runs(cand.candidate_id)
    assert len(runs) == 1
    assert val_svc.get_run(runs[0].validation_id).validation_id == runs[0].validation_id


def test_no_shadow_live_oms_in_package():
    root = Path(__file__).resolve().parents[2] / "app" / "services" / "strategy_validation"
    forbidden = (
        "submit_order",
        "promote_to_shadow",
        "promote_to_live",
        "link_governance_active",
    )
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        text = ast.dump(tree)
        for token in forbidden:
            assert token not in text
