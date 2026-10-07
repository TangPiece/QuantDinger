"""Phase 8B：Strategy Candidate 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.strategy_candidate.protocol import ENGINE_VERSION
from app.services.strategy_candidate.runner import CandidateError, LineageImmutableError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strategy_candidate_golden.golden import (  # noqa: E402
    BACKTEST_HASH,
    CAND_VERSION,
    DATASET_HASH,
    EXPERIMENT_ID,
    MODEL_VERSION,
    REGISTRY_VERSION,
    STRATEGY_CODE,
    STRATEGY_HASH,
    make_candidate_env,
)


def test_engine_version():
    assert ENGINE_VERSION == "qd_strategy_candidate@1"


def test_create_from_research_lineage(tmp_path):
    svc, _, _ = make_candidate_env(tmp_path / "lineage")
    cand = svc.create_from_research(
        STRATEGY_CODE,
        candidate_version=CAND_VERSION,
        experiment_id=EXPERIMENT_ID,
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
    )
    assert cand.status == "DRAFT"
    assert cand.dataset_hash == DATASET_HASH
    assert cand.model_version == MODEL_VERSION
    assert cand.strategy_hash == STRATEGY_HASH
    assert cand.content_hash


def test_idempotent_create(tmp_path):
    svc, _, _ = make_candidate_env(tmp_path / "idem")
    c1 = svc.create_from_research(
        STRATEGY_CODE,
        candidate_version=CAND_VERSION,
        experiment_id=EXPERIMENT_ID,
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
    )
    c2 = svc.create_from_research(
        STRATEGY_CODE,
        candidate_version=CAND_VERSION,
        experiment_id=EXPERIMENT_ID,
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
    )
    assert c1.candidate_id == c2.candidate_id


def test_lineage_mismatch_reject(tmp_path):
    svc, _, _ = make_candidate_env(tmp_path / "mut")
    svc.create_from_research(
        STRATEGY_CODE,
        candidate_version=CAND_VERSION,
        experiment_id=EXPERIMENT_ID,
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
    )
    with pytest.raises(LineageImmutableError):
        svc.create_from_research(
            STRATEGY_CODE,
            candidate_version=CAND_VERSION,
            experiment_id=EXPERIMENT_ID,
            backtest_hash=BACKTEST_HASH,
            strategy_hash=STRATEGY_HASH,
            dataset_hash="mutated_dh",
        )


def test_state_machine_happy_path(tmp_path):
    svc, _, _ = make_candidate_env(tmp_path / "fsm")
    cand = svc.create_from_research(
        STRATEGY_CODE,
        candidate_version=CAND_VERSION,
        experiment_id=EXPERIMENT_ID,
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
    )
    cand = svc.generate(cand.candidate_id)
    assert cand.status == "GENERATED"
    assert cand.lineage_frozen
    cand = svc.start_evaluating(cand.candidate_id)
    cand = svc.mark_ready(cand.candidate_id)
    cand = svc.mark_validated(cand.candidate_id, operator="tester", reason="golden")
    assert cand.status == "VALIDATED"


def test_cannot_skip_to_validated(tmp_path):
    svc, _, _ = make_candidate_env(tmp_path / "skip")
    cand = svc.create_from_research(
        STRATEGY_CODE,
        candidate_version=CAND_VERSION,
        experiment_id=EXPERIMENT_ID,
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
    )
    with pytest.raises(CandidateError):
        svc.mark_validated(cand.candidate_id)


def test_reject_and_expire_paths(tmp_path):
    svc, _, _ = make_candidate_env(tmp_path / "fail")
    cand = svc.create_from_research(
        STRATEGY_CODE,
        candidate_version=CAND_VERSION,
        experiment_id=EXPERIMENT_ID,
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
    )
    cand = svc.generate(cand.candidate_id)
    cand = svc.start_evaluating(cand.candidate_id)
    rejected = svc.reject(cand.candidate_id, reason="metrics")
    assert rejected.status == "REJECTED"

    cand2 = svc.create_from_research(
        STRATEGY_CODE,
        candidate_version="cv8b_expire",
        experiment_id=EXPERIMENT_ID,
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
    )
    cand2 = svc.generate(cand2.candidate_id)
    cand2 = svc.start_evaluating(cand2.candidate_id)
    cand2 = svc.mark_ready(cand2.candidate_id)
    expired = svc.expire(cand2.candidate_id, reason="ttl")
    assert expired.status == "EXPIRED"


def test_promote_to_registry(tmp_path):
    svc, reg_svc, _ = make_candidate_env(tmp_path / "promote")
    cand = svc.create_from_research(
        STRATEGY_CODE,
        candidate_version=CAND_VERSION,
        experiment_id=EXPERIMENT_ID,
        backtest_hash=BACKTEST_HASH,
        strategy_hash=STRATEGY_HASH,
    )
    for step in (
        lambda: svc.generate(cand.candidate_id),
        lambda: svc.start_evaluating(cand.candidate_id),
        lambda: svc.mark_ready(cand.candidate_id),
        lambda: svc.mark_validated(cand.candidate_id),
    ):
        step()
    cand = svc.get(cand.candidate_id)
    _, prom, ver = svc.promote_to_registry(
        cand.candidate_id,
        target_strategy_version=REGISTRY_VERSION,
        operator="tester",
        reason="golden promote",
    )
    assert prom.to_state == "REGISTERED"
    assert prom.version_id == ver.version_id
    reg_ver = reg_svc.get_version(STRATEGY_CODE, REGISTRY_VERSION)
    assert reg_ver.dataset_hash == DATASET_HASH
    assert reg_ver.strategy_hash == STRATEGY_HASH
    promotions = svc.get_promotions(cand.candidate_id)
    assert any(p.to_state == "REGISTERED" for p in promotions)


def test_no_shadow_live_gate_in_package():
    root = Path(__file__).resolve().parents[2] / "app" / "services" / "strategy_candidate"
    forbidden = (
        "submit_order",
        "promote_to_shadow",
        "promote_to_live",
        "validate_gate",
        "link_governance_active",
    )
    for py in root.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        text = ast.dump(tree)
        for token in forbidden:
            assert token not in text
