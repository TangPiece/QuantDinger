"""Phase 9F-8：Reproducible Training。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.services.research_data.model_platform.runner import ModelPlatformService
from app.services.research_data.model_reproducibility import (
    ENGINE_VERSION,
    ReproducibilityInject,
    ReproducibilityService,
)
from model_platform_golden.golden import (
    create_formal_version,
    golden_model_spec,
    make_model_platform_env,
)


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _env(tmp: Path):
    plat = make_model_platform_env(tmp / "plat")
    repro = ReproducibilityService(tmp / "repro", model_platform=plat)
    plat.bind_reproducibility_service(repro)
    return plat, repro


def _trained(plat: ModelPlatformService, *, code: str = "alpha_repro", version: str = "1.0.0"):
    model = plat.register_model(golden_model_spec(model_code=code))
    ver = create_formal_version(plat, model_id=model.model_id, version=version)
    run = plat.get_training_run(
        plat.get_version(ver.model_version_id).training_run_id
    )
    return model, ver, run


def test_engine_version():
    assert ENGINE_VERSION == "qd_model_reproducibility@1"


def test_no_auto_live_or_promote():
    assert not hasattr(ReproducibilityService, "auto_live")
    assert not hasattr(ReproducibilityService, "promote_strategy")
    assert not hasattr(ModelPlatformService, "promote_strategy")


def test_capture_on_formal_version(tmp_path: Path):
    plat, repro = _env(tmp_path / "cap")
    _, ver, run = _trained(plat)
    man = repro.get_manifest_for_training_run(run.training_run_id)
    assert man.immutable is True
    assert man.dataset_hash
    assert man.seeds.master_seed == run.random_seed
    tip = plat.get_repro_manifest(ver.model_version_id)
    assert tip.get("repro_manifest_id") == man.repro_manifest_id


def test_exact_or_numerical_match(tmp_path: Path):
    plat, repro = _env(tmp_path / "ok")
    _, _, run = _trained(plat, code="alpha_ok")
    rr = repro.reproduce(
        run.training_run_id,
        policy_code="REPRO_STRICT_V1",
        inject=ReproducibilityInject(
            skip_execute=True,
            artifact_checksum_original="a" * 64,
            artifact_checksum_reproduced="a" * 64,
            metrics_original={"loss": 0.1},
            metrics_reproduced={"loss": 0.1},
            predictions_original=[{"prediction": 1.0}],
            predictions_reproduced=[{"prediction": 1.0}],
        ),
    )
    assert rr.result == "EXACT_MATCH"
    assert rr.status == "SUCCEEDED"
    assert (repro.get_artifact_dir(rr.reproducibility_run_id) / "reproducibility_report.json").is_file()


def test_data_mismatch_partition(tmp_path: Path):
    plat, repro = _env(tmp_path / "data")
    _, _, run = _trained(plat, code="alpha_data")
    rr = repro.reproduce(
        run.training_run_id,
        inject=ReproducibilityInject(
            skip_execute=True,
            mutate_partition_checksum="f" * 64,
        ),
    )
    assert rr.result == "DATA_MISMATCH"
    assert rr.status == "FAILED"


def test_input_mismatch_snapshot_feature_processor(tmp_path: Path):
    plat, repro = _env(tmp_path / "inp")
    _, _, run = _trained(plat, code="alpha_inp")
    cases = (
        {"mutate_snapshot_id": "snap_other"},
        {"mutate_feature_set_hash": "9" * 64},
        {"mutate_processor_version": "processor@999"},
    )
    for mutate in cases:
        rr = repro.reproduce(
            run.training_run_id,
            inject=ReproducibilityInject(skip_execute=True, **mutate),
        )
        assert rr.result == "INPUT_MISMATCH", mutate


def test_code_mismatch(tmp_path: Path):
    plat, repro = _env(tmp_path / "code")
    _, _, run = _trained(plat, code="alpha_code")
    # re-capture with known commit then mutate
    # overwrite via new capture is blocked; mutate on reproduce uses source commit
    man = repro.get_manifest_for_training_run(run.training_run_id)
    # patch source commit in-memory for test by writing new training metadata path:
    # reproduce compares inject.mutate_code_commit vs source.code_commit
    # ensure source has a commit
    if not man.code_commit:
        man2 = man.model_copy(update={"code_commit": "git:deadbeef"})
        from app.services.research_data.model_reproducibility.writers import write_manifest

        write_manifest(repro._store, man2)
        repro._manifests[man2.repro_manifest_id] = man2
    rr = repro.reproduce(
        run.training_run_id,
        inject=ReproducibilityInject(skip_execute=True, mutate_code_commit="git:other"),
    )
    assert rr.result == "CODE_MISMATCH"


def test_dependency_and_env_mismatch(tmp_path: Path):
    plat, repro = _env(tmp_path / "dep")
    _, _, run = _trained(plat, code="alpha_dep")
    rr = repro.reproduce(
        run.training_run_id,
        inject=ReproducibilityInject(
            skip_execute=True, mutate_dependency_lock_hash="e" * 64
        ),
    )
    assert rr.result == "DEPENDENCY_MISMATCH"
    rr2 = repro.reproduce(
        run.training_run_id,
        inject=ReproducibilityInject(
            skip_execute=True, mutate_environment_hash="e" * 64
        ),
    )
    assert rr2.result == "ENV_MISMATCH"


def test_seed_mismatch(tmp_path: Path):
    plat, repro = _env(tmp_path / "seed")
    _, _, run = _trained(plat, code="alpha_seed")
    rr = repro.reproduce(
        run.training_run_id,
        inject=ReproducibilityInject(skip_execute=True, mutate_seed=999),
    )
    assert rr.result == "SEED_MISMATCH"


def test_non_deterministic(tmp_path: Path):
    plat, repro = _env(tmp_path / "nd")
    _, _, run = _trained(plat, code="alpha_nd")
    rr = repro.reproduce(
        run.training_run_id,
        policy_code="REPRO_STRICT_V1",
        inject=ReproducibilityInject(
            skip_execute=True,
            force_non_deterministic=True,
            artifact_checksum_original="a" * 64,
            artifact_checksum_reproduced="b" * 64,
            metrics_original={"loss": 0.1},
            metrics_reproduced={"loss": 0.1},
            predictions_original=[{"prediction": 1.0}],
            predictions_reproduced=[{"prediction": 1.0}],
        ),
    )
    assert rr.result == "NON_DETERMINISTIC"
    assert rr.status == "SUCCEEDED"


def test_source_run_and_version_immutable(tmp_path: Path):
    plat, repro = _env(tmp_path / "immut")
    _, ver, run = _trained(plat, code="alpha_immut")
    run_path = plat._store.training_run_path(training_run_id=run.training_run_id)
    ver_path = plat._store.version_path(model_version_id=ver.model_version_id)
    before_run = _file_sha(run_path)
    before_ver = _file_sha(ver_path)
    repro.reproduce(
        run.training_run_id,
        inject=ReproducibilityInject(
            skip_execute=True,
            mutate_seed=7,
        ),
    )
    assert _file_sha(run_path) == before_run
    assert _file_sha(ver_path) == before_ver


def test_numerical_match_policy(tmp_path: Path):
    plat, repro = _env(tmp_path / "num")
    _, _, run = _trained(plat, code="alpha_num")
    rr = repro.reproduce(
        run.training_run_id,
        policy_code="REPRO_NUMERICAL_V1",
        inject=ReproducibilityInject(
            skip_execute=True,
            artifact_checksum_original="a" * 64,
            artifact_checksum_reproduced="b" * 64,
            metrics_original={"ic": 0.08321},
            metrics_reproduced={"ic": 0.08318},
            predictions_original=[{"prediction": 1.0}, {"prediction": 2.0}],
            predictions_reproduced=[
                {"prediction": 1.0 + 1e-9},
                {"prediction": 2.0 + 1e-9},
            ],
        ),
    )
    assert rr.result == "NUMERICAL_MATCH"
