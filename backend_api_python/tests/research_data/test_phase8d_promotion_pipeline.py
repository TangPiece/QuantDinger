"""Phase 8D：Strategy Promotion Pipeline 验收。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from app.services.research_data.contracts import StrategyPromotionRunSummary
from app.services.strategy_promotion.protocol import ENGINE_VERSION
from app.services.strategy_promotion.runner import PromotionError, StrategyPromotionService

sys.path.insert(0, str(Path(__file__).resolve().parent))
from promotion_pipeline_golden.golden import (  # noqa: E402
    golden_promotion_metrics_inject,
    make_promotion_env,
    seed_promoted_registry,
)
from strategy_candidate_golden.golden import REGISTRY_VERSION, STRATEGY_CODE  # noqa: E402


def test_engine_version():
    assert ENGINE_VERSION == "qd_strategy_promotion@1"


def test_registered_to_shadow_happy_path(tmp_path):
    promo, cand_svc, reg_svc, val_svc, _ = make_promotion_env(tmp_path / "shadow")
    cand, _, validation_id = seed_promoted_registry(cand_svc, reg_svc, val_svc)
    req = promo.submit_request(
        strategy_code=STRATEGY_CODE,
        candidate_id=cand.candidate_id,
        validation_id=validation_id,
        strategy_version=REGISTRY_VERSION,
        to_environment="SHADOW",
        idempotency_key="idem_shadow_1",
    )
    run = promo.execute(req.request_id, inject=golden_promotion_metrics_inject())
    assert run.status == "COMPLETED"
    assert run.to_environment == "SHADOW"
    assert run.policy_content_hash
    assert any(s.stage == "SHADOW_SESSION" for s in run.stages)


def test_execute_requires_validation_passed(tmp_path):
    promo, cand_svc, reg_svc, val_svc, _ = make_promotion_env(tmp_path / "no_val")
    cand = seed_promoted_registry(cand_svc, reg_svc, val_svc)[0]
    with pytest.raises(PromotionError):
        promo.submit_request(
            strategy_code=STRATEGY_CODE,
            candidate_id=cand.candidate_id,
            validation_id="val_missing_fake",
            strategy_version=REGISTRY_VERSION,
            to_environment="SHADOW",
            idempotency_key="idem_no_val",
        )


def test_forbid_shadow_to_live(tmp_path):
    promo, cand_svc, reg_svc, val_svc, _ = make_promotion_env(tmp_path / "skip")
    cand, _, validation_id = seed_promoted_registry(cand_svc, reg_svc, val_svc)
    with pytest.raises(PromotionError):
        promo.submit_request(
            strategy_code=STRATEGY_CODE,
            candidate_id=cand.candidate_id,
            validation_id=validation_id,
            strategy_version=REGISTRY_VERSION,
            to_environment="LIVE",
            idempotency_key="idem_skip_live",
            from_environment="SHADOW",
        )


def test_idempotent_execute(tmp_path):
    promo, cand_svc, reg_svc, val_svc, _ = make_promotion_env(tmp_path / "idem")
    cand, _, validation_id = seed_promoted_registry(cand_svc, reg_svc, val_svc)
    req = promo.submit_request(
        strategy_code=STRATEGY_CODE,
        candidate_id=cand.candidate_id,
        validation_id=validation_id,
        strategy_version=REGISTRY_VERSION,
        to_environment="SHADOW",
        idempotency_key="idem_exec_twice",
    )
    inj = golden_promotion_metrics_inject()
    r1 = promo.execute(req.request_id, inject=inj)
    r2 = promo.execute(req.request_id, inject=inj)
    assert r1.pipeline_run_id == r2.pipeline_run_id
    assert r1.status == r2.status == "COMPLETED"


def test_lock_blocks_second_in_progress(tmp_path):
    promo, cand_svc, reg_svc, val_svc, _ = make_promotion_env(tmp_path / "lock")
    cand, _, validation_id = seed_promoted_registry(cand_svc, reg_svc, val_svc)
    req = promo.submit_request(
        strategy_code=STRATEGY_CODE,
        candidate_id=cand.candidate_id,
        validation_id=validation_id,
        strategy_version=REGISTRY_VERSION,
        to_environment="SHADOW",
        idempotency_key="idem_lock_a",
    )
    promo._registry.upsert_strategy_promotion_run(
        StrategyPromotionRunSummary(
            pipeline_run_id="promo_run_blocking",
            request_id="promo_req_blocking",
            strategy_code=STRATEGY_CODE,
            from_environment="REGISTERED",
            to_environment="SHADOW",
            status="IN_PROGRESS",
            started_at="2020-01-01T00:00:00+00:00",
        )
    )
    with pytest.raises(PromotionError, match="IN_PROGRESS"):
        promo.execute(req.request_id, inject=golden_promotion_metrics_inject())


def test_live_without_approval_rejected(tmp_path):
    promo, cand_svc, reg_svc, val_svc, gov = make_promotion_env(tmp_path / "live_no_appr")
    cand, _, validation_id = seed_promoted_registry(cand_svc, reg_svc, val_svc, governance=gov)
    inj = golden_promotion_metrics_inject()
    for env, key in (
        ("SHADOW", "idem_cl_path_1"),
        ("CONTROLLED_LIVE", "idem_cl_path_2"),
    ):
        req = promo.submit_request(
            strategy_code=STRATEGY_CODE,
            candidate_id=cand.candidate_id,
            validation_id=validation_id,
            strategy_version=REGISTRY_VERSION,
            to_environment=env,
            idempotency_key=key,
        )
        promo.execute(req.request_id, inject=inj)
    req_live = promo.submit_request(
        strategy_code=STRATEGY_CODE,
        candidate_id=cand.candidate_id,
        validation_id=validation_id,
        strategy_version=REGISTRY_VERSION,
        to_environment="LIVE",
        idempotency_key="idem_live_no_appr",
    )
    with pytest.raises(PromotionError, match="approval"):
        promo.execute(req_live.request_id, inject=inj)


def test_live_with_approval_fake(tmp_path):
    promo, cand_svc, reg_svc, val_svc, gov = make_promotion_env(tmp_path / "live_ok")
    cand, _, validation_id = seed_promoted_registry(cand_svc, reg_svc, val_svc, governance=gov)
    inj = golden_promotion_metrics_inject()
    for env, key in (
        ("SHADOW", "live_ok_1"),
        ("CONTROLLED_LIVE", "live_ok_2"),
    ):
        req = promo.submit_request(
            strategy_code=STRATEGY_CODE,
            candidate_id=cand.candidate_id,
            validation_id=validation_id,
            strategy_version=REGISTRY_VERSION,
            to_environment=env,
            idempotency_key=key,
        )
        promo.execute(req.request_id, inject=inj)
    req_live = promo.submit_request(
        strategy_code=STRATEGY_CODE,
        candidate_id=cand.candidate_id,
        validation_id=validation_id,
        strategy_version=REGISTRY_VERSION,
        to_environment="LIVE",
        idempotency_key="live_ok_3",
    )
    promo.approve(req_live.request_id, operator="test", token="tok")
    run = promo.execute(req_live.request_id, inject=inj)
    assert run.to_environment == "LIVE"
    assert run.governance_state == "LIVE"


def test_rollback_record(tmp_path):
    promo, cand_svc, reg_svc, val_svc, gov = make_promotion_env(tmp_path / "rb")
    seed_promoted_registry(cand_svc, reg_svc, val_svc, governance=gov)
    from app.services.strategy_registry.identity import strategy_id_from_code

    sid = strategy_id_from_code(STRATEGY_CODE)
    gov.register_strategy_version(strategy_id=sid, strategy_version=REGISTRY_VERSION)
    gov.register_strategy_version(strategy_id=sid, strategy_version="sv_prev_stable")
    gov._lifecycle[sid] = gov._lifecycle[sid].model_copy(
        update={"active_version": REGISTRY_VERSION, "state": "SHADOW"}
    )
    rec = promo.rollback(
        STRATEGY_CODE,
        to_version="sv_prev_stable",
        reason="verify",
        operator="test",
    )
    assert rec.rollback_id.startswith("promo_rb_")
    assert rec.to_version == "sv_prev_stable"


def test_no_oms_in_package():
    root = Path(__file__).resolve().parents[2] / "app" / "services" / "strategy_promotion"
    forbidden = ("submit_order", "promote_to_live", "mutate_version")
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        text = ast.dump(tree)
        for token in forbidden:
            assert token not in text
