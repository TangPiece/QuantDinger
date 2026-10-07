"""Phase 9A — Research Dataset Platform。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.research_data.dataset_platform.hashing import compute_domain_dataset_hash
from app.services.research_data.dataset_platform.protocol import ENGINE_VERSION
from app.services.research_data.dataset_platform.runner import DatasetPlatformError
from dataset_platform_golden.golden import (
    GOLDEN_DATASET_REF,
    golden_bad_pit_inject,
    golden_dataset_definition,
    golden_empty_snapshot_inject,
    golden_snapshot_items,
    make_dataset_platform_env,
)


def test_engine_version():
    assert ENGINE_VERSION == "qd_dataset_platform@1"


def test_build_manifest_and_hash_stable(tmp_path):
    svc, _reg, dq, _store = make_dataset_platform_env(tmp_path / "a")
    definition = golden_dataset_definition()
    h1 = svc.build_and_register(definition, snapshot_items=golden_snapshot_items())
    h2 = svc.get(GOLDEN_DATASET_REF)
    assert h1.dataset_hash == h2.dataset_hash
    assert len(h1.dataset_hash) == 64
    assert h1.manifest_uri
    manifest = svc.get_manifest(GOLDEN_DATASET_REF)
    assert manifest.dataset_hash == h1.dataset_hash
    assert manifest.immutable is True

    dq_handle = dq.dataset(GOLDEN_DATASET_REF)
    assert dq_handle.dataset_hash == h1.dataset_hash
    assert dq_handle.manifest_uri


def test_feature_change_new_hash(tmp_path):
    svc, _reg, _dq, _store = make_dataset_platform_env(tmp_path / "feat")
    base = svc.build_and_register(
        golden_dataset_definition(), snapshot_items=golden_snapshot_items()
    )
    bumped = golden_dataset_definition(features=["close", "volume"])
    bumped = bumped.model_copy(update={"version": "1.0.1"})
    h2 = svc.build_and_register(bumped, snapshot_items=golden_snapshot_items())
    assert h2.dataset_hash != base.dataset_hash


def test_immutability_reject_and_bump(tmp_path):
    svc, _reg, _dq, _store = make_dataset_platform_env(tmp_path / "imm")
    definition = golden_dataset_definition()
    svc.build_and_register(definition, snapshot_items=golden_snapshot_items())
    mutated = definition.model_copy(
        update={"features": ["close", "volume", "open", "high", "low", "amount", "vwap", "extra"]}
    )
    with pytest.raises(DatasetPlatformError):
        svc.build_and_register(mutated, snapshot_items=golden_snapshot_items())

    v2 = definition.model_copy(update={"version": "2.0.0"})
    ok = svc.build_and_register(v2, snapshot_items=golden_snapshot_items())
    assert ok.definition.version == "2.0.0"


def test_quality_gate_rejects_inject(tmp_path):
    svc, _reg, _dq, _store = make_dataset_platform_env(tmp_path / "gate")
    definition = golden_dataset_definition()
    with pytest.raises(DatasetPlatformError):
        svc.build_and_register(
            definition,
            snapshot_items=golden_snapshot_items(),
            inject=golden_bad_pit_inject(),
        )
    with pytest.raises(DatasetPlatformError):
        svc.build_and_register(
            definition,
            snapshot_items=golden_snapshot_items(),
            inject=golden_empty_snapshot_inject(),
        )


def test_artifact_files_exist(tmp_path):
    svc, _reg, _dq, _store = make_dataset_platform_env(tmp_path / "files")
    definition = golden_dataset_definition()
    handle = svc.build_and_register(definition, snapshot_items=golden_snapshot_items())
    manifest = svc.get_manifest(GOLDEN_DATASET_REF)
    assert Path(handle.manifest_uri).is_file()
    store = svc._store  # noqa: SLF001 — 验收本地 def.json
    def_path = store.def_path(definition)
    assert def_path.is_file()
    assert manifest.def_r2_key


def test_list_datasets_prefix(tmp_path):
    svc, _reg, _dq, _store = make_dataset_platform_env(tmp_path / "list")
    svc.build_and_register(
        golden_dataset_definition(), snapshot_items=golden_snapshot_items()
    )
    refs = svc.list_datasets(code_prefix="PHASE9A")
    assert GOLDEN_DATASET_REF in refs


def test_package_no_trading_db_imports():
    root = Path(__file__).resolve().parents[2] / "app" / "services" / "research_data" / "dataset_platform"
    forbidden = ("trading_db", "submit_order", "production_oms", "psycopg")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for tok in forbidden:
            assert tok not in text, f"{path.name} contains {tok}"


def test_hash_matches_registry(tmp_path):
    svc, reg, _dq, _store = make_dataset_platform_env(tmp_path / "hash")
    definition = golden_dataset_definition()
    handle = svc.build_and_register(definition, snapshot_items=golden_snapshot_items())
    expected = compute_domain_dataset_hash(definition)
    reg_handle = reg.get_dataset(GOLDEN_DATASET_REF)
    assert handle.dataset_hash == expected == reg_handle.dataset_hash
