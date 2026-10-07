"""Phase 9F-1 — Model Contract & Registry。"""

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
    assert not hasattr(ModelPlatformService, "predict")
    assert not hasattr(ModelPlatformService, "evaluate_model")
    assert not hasattr(ModelPlatformService, "auto_live")
    assert not hasattr(ModelPlatformService, "promote_strategy")


def test_model_ne_version(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "sep")
    model = svc.register_model(golden_model_spec())
    version = svc.register_version(model.model_id, golden_version_spec())
    assert model.model_id != version.model_version_id
    assert version.model_code == GOLDEN_MODEL_CODE
    assert version.lifecycle == "DRAFT"
    assert len(version.version_content_hash) == 64
    assert len(version.model_config_hash) == 64
    assert version.dataset_hash


def test_config_hash_stable():
    h1 = compute_model_config_hash(GOLDEN_CONFIG)
    h2 = compute_model_config_hash(dict(reversed(list(GOLDEN_CONFIG.items()))))
    assert h1 == h2
    assert h1 == compute_model_config_hash(GOLDEN_CONFIG)


def test_training_run_immutable(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "run")
    model = svc.register_model(golden_model_spec())
    version = svc.register_version(model.model_id, golden_version_spec())
    rid = "trun_golden_fixed01"
    run1 = svc.create_training_run(
        golden_training_run_spec(
            model_id=model.model_id,
            model_version_id=version.model_version_id,
            training_run_id=rid,
        )
    )
    run2 = svc.create_training_run(
        golden_training_run_spec(
            model_id=model.model_id,
            model_version_id=version.model_version_id,
            training_run_id=rid,
        )
    )
    assert run1.training_run_id == run2.training_run_id
    assert run1.training_run_hash == run2.training_run_hash

    with pytest.raises(ModelPlatformError):
        svc.create_training_run(
            golden_training_run_spec(
                model_id=model.model_id,
                model_version_id=version.model_version_id,
                training_run_id=rid,
                random_seed=99,
            )
        )


def test_lifecycle_activate_retire(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "life")
    model = svc.register_model(golden_model_spec())
    version = svc.register_version(model.model_id, golden_version_spec())
    for target in ("TRAINING", "TRAINED", "EVALUATING", "VALIDATED", "APPROVED"):
        version = svc.transition(version.model_version_id, target)  # type: ignore[arg-type]
    active = svc.activate(version.model_version_id)
    assert active.lifecycle == "ACTIVE"
    hits = svc.search(ModelSearchQuery(lifecycle=["ACTIVE"], tags_any=["golden"]))
    assert any(v.model_version_id == active.model_version_id for v in hits["versions"])

    svc.retire(active.model_version_id)
    with pytest.raises(ModelLifecycleError):
        svc.activate(active.model_version_id)
    still = svc.get_version(active.model_version_id)
    assert still.lifecycle == "RETIRED"


def test_illegal_transition(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "bad")
    model = svc.register_model(golden_model_spec())
    version = svc.register_version(model.model_id, golden_version_spec())
    with pytest.raises(ModelLifecycleError):
        svc.transition(version.model_version_id, "ACTIVE")


def test_artifact_and_legacy(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "art")
    model = svc.register_model(golden_model_spec())
    version = svc.register_version(model.model_id, golden_version_spec())
    art = svc.register_artifact(golden_artifact_spec(version.model_version_id))
    bound = svc.get_version(version.model_version_id)
    assert bound.artifact_id == art.artifact_id
    legacy = svc.to_legacy_definition(model.model_code, version=GOLDEN_VERSION)
    assert legacy.code == GOLDEN_MODEL_CODE
    assert legacy.version == GOLDEN_VERSION
