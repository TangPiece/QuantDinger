"""Phase 9F — Model Contract & Lineage（9F-1/9F-2）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.research_data.model_platform.hashing import compute_model_config_hash
from app.services.research_data.model_platform.lifecycle import ModelLifecycleError
from app.services.research_data.model_platform.protocol import ENGINE_VERSION, ModelSearchQuery
from app.services.research_data.model_platform.runner import (
    ModelPlatformError,
    ModelPlatformService,
)
from model_platform_golden.golden import (
    GOLDEN_CONFIG,
    GOLDEN_MODEL_CODE,
    GOLDEN_VERSION,
    create_formal_version,
    create_succeeded_run,
    draft_stub_inject,
    formal_inject,
    golden_artifact_spec,
    golden_model_spec,
    golden_training_run_spec,
    golden_version_spec,
    make_model_platform_env,
)


def test_engine_version():
    assert ENGINE_VERSION == "qd_model_platform@1"


def test_no_forbidden_apis():
    assert not hasattr(ModelPlatformService, "train")
    assert hasattr(ModelPlatformService, "predict")  # 9F-4 薄 Predict（非 Signal）
    assert not hasattr(ModelPlatformService, "evaluate_model")
    assert not hasattr(ModelPlatformService, "auto_live")
    assert not hasattr(ModelPlatformService, "promote_strategy")


def test_register_version_requires_run_or_stub(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "rej")
    model = svc.register_model(golden_model_spec())
    with pytest.raises(ModelPlatformError):
        svc.register_version(model.model_id, golden_version_spec())


def test_draft_stub_still_works(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "stub")
    model = svc.register_model(golden_model_spec())
    version = svc.register_version(
        model.model_id, golden_version_spec(), inject=draft_stub_inject()
    )
    assert version.lifecycle == "DRAFT"
    assert model.model_id != version.model_version_id


def test_config_hash_stable():
    h1 = compute_model_config_hash(GOLDEN_CONFIG)
    h2 = compute_model_config_hash(dict(reversed(list(GOLDEN_CONFIG.items()))))
    assert h1 == h2


def test_training_run_immutable(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "run")
    model = svc.register_model(golden_model_spec())
    rid = "trun_golden_fixed01"
    run1 = svc.create_training_run(
        golden_training_run_spec(model_id=model.model_id, training_run_id=rid)
    )
    run2 = svc.create_training_run(
        golden_training_run_spec(model_id=model.model_id, training_run_id=rid)
    )
    assert run1.training_run_hash == run2.training_run_hash
    with pytest.raises(ModelPlatformError):
        svc.create_training_run(
            golden_training_run_spec(
                model_id=model.model_id, training_run_id=rid, random_seed=99
            )
        )


def test_create_version_from_succeeded_run(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "formal")
    model = svc.register_model(golden_model_spec())
    version = create_formal_version(svc, model_id=model.model_id)
    assert version.lifecycle == "TRAINED"
    assert version.training_run_id
    assert version.artifact_id
    assert len(version.version_content_hash) == 64
    lineage = svc.get_lineage(version.model_version_id)
    assert lineage["dataset_hash"]
    assert lineage["feature_set_hash"]
    assert lineage["training_run_id"]
    assert lineage["artifact_id"]
    assert lineage["repro_manifest_uri"]
    repro = svc.get_repro_manifest(version.model_version_id)
    assert repro["artifact_checksum"]
    assert repro["version_content_hash"] == version.version_content_hash
    art = svc.get_artifact_for_version(version.model_version_id)
    assert art.artifact_id == version.artifact_id


def test_reject_non_succeeded_run(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "ns")
    model = svc.register_model(golden_model_spec())
    run = svc.create_training_run(
        golden_training_run_spec(model_id=model.model_id, training_run_id="trun_q")
    )
    with pytest.raises(ModelPlatformError):
        svc.create_version_from_run(
            run.training_run_id,
            version="2.0.0",
            lineage_spec=golden_version_spec(version="2.0.0"),
            artifact_spec=golden_artifact_spec(),
            inject=formal_inject(),
        )


def test_reject_bad_checksum_and_missing_lineage(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "badcs")
    model = svc.register_model(golden_model_spec())
    run = create_succeeded_run(svc, model_id=model.model_id, training_run_id="trun_cs")
    with pytest.raises(ModelPlatformError):
        svc.create_version_from_run(
            run.training_run_id,
            version="3.0.0",
            lineage_spec=golden_version_spec(version="3.0.0"),
            artifact_spec=golden_artifact_spec(checksum="deadbeef"),
            inject=formal_inject(),
        )
    with pytest.raises(ModelPlatformError):
        svc.create_version_from_run(
            run.training_run_id,
            version="3.1.0",
            lineage_spec=golden_version_spec(version="3.1.0", snapshot_id=""),
            artifact_spec=golden_artifact_spec(),
            inject=formal_inject(),
        )


def test_reject_duplicate_version(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "dup")
    model = svc.register_model(golden_model_spec())
    create_formal_version(svc, model_id=model.model_id, version="1.0.0")
    with pytest.raises(ModelPlatformError):
        create_formal_version(
            svc, model_id=model.model_id, version="1.0.0", training_run_id="trun_dup2"
        )


def test_reject_artifact_rebind_and_delete(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "rebind")
    model = svc.register_model(golden_model_spec())
    version = create_formal_version(svc, model_id=model.model_id)
    with pytest.raises(ModelPlatformError):
        svc.register_artifact(golden_artifact_spec(version.model_version_id))
    with pytest.raises(ModelPlatformError):
        svc.delete_version(version.model_version_id)


def test_lifecycle_activate_retire_and_active_query(tmp_path: Path):
    from app.services.research_data.model_platform.protocol import ModelPlatformInject

    svc = make_model_platform_env(tmp_path / "life")
    model = svc.register_model(golden_model_spec())
    version = create_formal_version(svc, model_id=model.model_id)
    version = svc.transition(version.model_version_id, "EVALUATING")
    version = svc.transition(version.model_version_id, "VALIDATED")
    with pytest.raises(ModelPlatformError):
        svc.transition(version.model_version_id, "APPROVED")
    version, approval = svc.approve_version(
        version.model_version_id,
        operator="tester",
        reason="golden",
        inject=ModelPlatformInject(skip_approval_gate=True),
    )
    assert approval.decision == "APPROVED"
    assert version.lifecycle == "APPROVED"
    active = svc.activate(version.model_version_id, operator="tester", reason="go")
    assert active.lifecycle == "ACTIVE"
    assert svc.get_active_version(model.model_id).model_version_id == active.model_version_id
    hits = svc.search(ModelSearchQuery(lifecycle=["ACTIVE"], tags_any=["golden"]))
    assert any(v.model_version_id == active.model_version_id for v in hits["versions"])
    assert svc.list_activations(model_id=model.model_id)

    svc.retire(active.model_version_id)
    with pytest.raises(ModelLifecycleError):
        svc.activate(active.model_version_id)
    with pytest.raises(ModelPlatformError):
        svc.get_active_version(model.model_id)


def test_illegal_transition_from_trained(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "bad")
    model = svc.register_model(golden_model_spec())
    version = create_formal_version(svc, model_id=model.model_id)
    with pytest.raises(ModelLifecycleError):
        svc.transition(version.model_version_id, "ACTIVE")


def test_succeeded_status_immutable(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "st")
    model = svc.register_model(golden_model_spec())
    run = create_succeeded_run(svc, model_id=model.model_id, training_run_id="trun_st")
    with pytest.raises(ModelPlatformError):
        svc.update_training_run_status(run.training_run_id, "FAILED")


def test_legacy_bridge(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "leg")
    model = svc.register_model(golden_model_spec())
    create_formal_version(svc, model_id=model.model_id)
    legacy = svc.to_legacy_definition(model.model_code, version=GOLDEN_VERSION)
    assert legacy.code == GOLDEN_MODEL_CODE
    assert legacy.version == GOLDEN_VERSION
