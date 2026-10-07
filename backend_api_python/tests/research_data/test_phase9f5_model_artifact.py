"""Phase 9F-5：Model Artifact Bundle Store / Loader / immutability。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.research_data.model_platform.artifact_fsm import (
    assert_artifact_status_transition,
)
from app.services.research_data.model_platform.artifact_manifest import MANIFEST_SCHEMA
from app.services.research_data.model_platform.bundle_store import sha256_bytes
from app.services.research_data.model_platform.runner import ModelPlatformError
from model_platform_golden.golden import (
    create_formal_version,
    formal_inject,
    golden_job_spec,
    golden_model_spec,
    make_model_platform_env,
)


def test_put_bundle_available_and_manifest(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "put")
    model = svc.register_model(golden_model_spec())
    job = svc.submit_training_job(
        golden_job_spec(model_id=model.model_id, force_new=True, idempotency_key="a1")
    )
    run = svc.execute_training_run(job.run_ids[0], inject=formal_inject())
    assert run.status == "SUCCEEDED"
    ver = svc.get_version(run.model_version_id)
    art = svc.get_artifact(ver.artifact_id)
    assert art.status == "AVAILABLE"
    assert art.checksum_algorithm == "SHA256"
    assert art.producer_type == "training_run"
    assert art.producer_id == run.training_run_id
    assert art.immutable_at is not None

    bundle = Path(art.artifact_uri).parent
    assert (bundle / "model.bin").is_file()
    assert (bundle / "manifest.json").is_file()
    assert (bundle / "checksum.sha256").is_file()
    man = (bundle / "manifest.json").read_text(encoding="utf-8")
    assert MANIFEST_SCHEMA in man or "model_artifact_manifest" in man
    assert svc.verify_artifact(art.artifact_id) is True


def test_tamper_rejects_verify_and_load(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "tamper")
    model = svc.register_model(golden_model_spec())
    ver = create_formal_version(svc, model_id=model.model_id)
    art = svc.get_artifact(ver.artifact_id)
    bin_path = Path(art.artifact_uri)
    bin_path.write_bytes(b"TAMPERED_PAYLOAD_XXXX")
    with pytest.raises(ModelPlatformError):
        svc.verify_artifact(art.artifact_id)
    art2 = svc.get_artifact(ver.artifact_id)
    assert art2.status == "CORRUPTED"
    with pytest.raises(ModelPlatformError):
        svc.load_model_artifact(ver.model_version_id)


def test_delete_bound_artifact_rejected(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "del")
    model = svc.register_model(golden_model_spec())
    ver = create_formal_version(svc, model_id=model.model_id)
    with pytest.raises(ModelPlatformError):
        svc.delete_artifact(ver.artifact_id)


def test_two_versions_distinct_artifacts(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "two")
    model = svc.register_model(golden_model_spec())
    v1 = create_formal_version(svc, model_id=model.model_id, version="1.0.0")
    v2 = create_formal_version(
        svc, model_id=model.model_id, version="2.0.0", training_run_id="trun_v2"
    )
    assert v1.artifact_id != v2.artifact_id
    loaded = svc.load_model_artifact(v1.model_version_id)
    assert loaded.artifact_id == v1.artifact_id
    assert Path(loaded.bin_path).is_file()


def test_cache_reuse(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "cache")
    model = svc.register_model(golden_model_spec())
    ver = create_formal_version(svc, model_id=model.model_id)
    a = svc.load_model_artifact(ver.model_version_id)
    assert a.from_cache is False
    b = svc.load_model_artifact(ver.model_version_id)
    assert b.from_cache is True
    assert a.checksum == b.checksum


def test_cache_mismatch_redownload(tmp_path: Path):
    svc = make_model_platform_env(tmp_path / "cachebad")
    model = svc.register_model(golden_model_spec())
    ver = create_formal_version(svc, model_id=model.model_id)
    first = svc.load_model_artifact(ver.model_version_id)
    first.bin_path.write_bytes(b"bad-cache-bytes")
    again = svc.load_model_artifact(ver.model_version_id)
    assert again.from_cache is False
    assert sha256_bytes(again.bin_path.read_bytes()) == again.checksum


def test_fsm_illegal_transition():
    with pytest.raises(Exception):
        assert_artifact_status_transition("AVAILABLE", "UPLOADING")


def test_no_qlib_in_model_platform():
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "research_data"
        / "model_platform"
    )
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "import qlib" not in text
        assert "from qlib" not in text
        assert "from app.services.research_data.model_training" not in text
