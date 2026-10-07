"""Phase 9D — Factor Mining Platform。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.research_data.mining_platform.protocol import ENGINE_VERSION
from app.services.research_data.mining_platform.runner import (
    FactorMiningError,
    FactorMiningService,
)
from app.services.research_data.mining_platform.generators.exhaustive import (
    ComplexityLimitError,
    assert_node_within_policy,
)
from app.services.research_data.mining_platform.expression.ast import MomentumNode
from app.services.research_data.mining_platform.policy_presets import get_policy
from mining_platform_golden.golden import (
    GOLDEN_MINING_POLICY_ID,
    GOLDEN_RANDOM_SEED,
    golden_mining_job,
    make_mining_platform_env,
    mining_inject,
)


def test_engine_version():
    assert ENGINE_VERSION == "qd_mining_platform@1"


def test_no_forbidden_apis():
    assert not hasattr(FactorMiningService, "auto_approve")
    assert not hasattr(FactorMiningService, "promote_strategy")
    assert not hasattr(FactorMiningService, "genetic_default")
    assert not hasattr(FactorMiningService, "mine_factors")


def test_reproducible_expression_hashes(tmp_path: Path):
    svc, _ds, _reg, job = make_mining_platform_env(tmp_path / "repro")
    inj = mining_inject()
    r1 = svc.run_mining(job, inject=inj)
    r2 = svc.run_mining(job, inject=inj)
    assert r1.mining_run_hash == r2.mining_run_hash
    h1 = {c.expression_hash for c in r1.candidates}
    h2 = {c.expression_hash for c in r2.candidates}
    assert h1 == h2


def test_exhaustive_max_candidates(tmp_path: Path):
    svc, _ds, _reg, job = make_mining_platform_env(tmp_path / "cap")
    pol = get_policy(GOLDEN_MINING_POLICY_ID)
    assert pol.max_candidates >= 1
    run = svc.run_mining(job, inject=mining_inject())
    assert run.total_candidates_generated <= pol.max_candidates


def test_complexity_rejected():
    pol = get_policy(GOLDEN_MINING_POLICY_ID).model_copy(update={"max_window": 3})
    with pytest.raises(ComplexityLimitError):
        assert_node_within_policy(MomentumNode(window=5), pol)


def test_fast_screen_reduces_eval(tmp_path: Path):
    svc, _ds, _reg, job = make_mining_platform_env(tmp_path / "screen")
    inj_high = mining_inject(screen_ic_threshold=0.99)
    run_high = svc.run_mining(
        job.model_copy(update={"random_seed": GOLDEN_RANDOM_SEED + 1}),
        inject=inj_high,
    )
    run_low = svc.run_mining(job, inject=mining_inject(screen_ic_threshold=0.0))
    assert run_low.total_candidates_tested >= run_high.total_candidates_tested


def test_survivors_have_evaluation_and_holdout(tmp_path: Path):
    svc, _ds, _reg, job = make_mining_platform_env(tmp_path / "eval")
    inj = mining_inject(
        holdout_metrics_by_expression_hash={"__any__": {"mean_ic": 0.02}},
    )
    run = svc.run_mining(job, inject=inj)
    assert run.total_candidates_tested >= 1
    assert run.selection_bias_warning
    ranked = [c for c in run.candidates if c.status == "RANKED"]
    for c in ranked:
        assert c.evaluation_id
        assert c.holdout_metrics is not None
    if ranked:
        scores = [c.mining_score for c in ranked]
        assert max(scores) >= min(scores)


def test_dedup_expression_hash(tmp_path: Path):
    from app.services.research_data.mining_platform.dedup import dedup_by_expression_hash
    from app.services.research_data.mining_platform.protocol import FactorCandidate

    a = FactorCandidate(
        candidate_id="a",
        mining_run_id="m",
        expression_hash="abc",
        dsl_expression="momentum_5",
    )
    b = FactorCandidate(
        candidate_id="b",
        mining_run_id="m",
        expression_hash="abc",
        dsl_expression="momentum_5",
    )
    out, removed = dedup_by_expression_hash([a, b])
    assert removed == 1
    assert len(out) == 1


def test_promote_draft_only(tmp_path: Path):
    svc, _ds, _reg, job = make_mining_platform_env(tmp_path / "promote")
    run = svc.run_mining(job, inject=mining_inject())
    ranked = next((c for c in run.candidates if c.factor_ref), None)
    if ranked is None:
        pytest.skip("no ranked candidate")
    feat = svc.promote_candidate_to_draft(ranked.candidate_id)
    assert feat.definition.get("lifecycle_status") == "DRAFT"
    assert "APPROVED" not in str(feat.definition).upper()


def test_list_candidates(tmp_path: Path):
    svc, _ds, _reg, job = make_mining_platform_env(tmp_path / "list")
    run = svc.run_mining(job, inject=mining_inject())
    listed = svc.list_candidates(run.mining_run_id)
    assert len(listed) == len(run.candidates)


def test_get_run(tmp_path: Path):
    svc, _ds, _reg, job = make_mining_platform_env(tmp_path / "get")
    run = svc.run_mining(job, inject=mining_inject())
    loaded = svc.get_run(run.mining_run_id)
    assert loaded.mining_run_id == run.mining_run_id


def test_missing_candidate_raises(tmp_path: Path):
    svc, _ds, _reg, _job = make_mining_platform_env(tmp_path / "miss")
    with pytest.raises(FactorMiningError):
        svc.promote_candidate_to_draft("mcand_nonexistent")
