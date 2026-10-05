"""Phase 2D：Model 契约 / artifact_id / 训练隔离（LightGBM）。"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.research_data.contracts import (
    ArtifactRecord,
    ModelDefinition,
    ModelVersionRecord,
)
from app.services.research_data.ingest.build_golden import GOLDEN_DATASET_CODE
from app.services.research_data.model_training import (
    ModelTrainSpec,
    ModelTrainer,
    compute_config_digest,
    compute_model_artifact_id,
    builtin_lgb_baseline_model,
)
from app.services.research_data.qlib_adapter import (
    QlibAdapter,
    ResearchDatasetSpec,
    SegmentRange,
    SegmentSpec,
    VersionResolver,
    builtin_qd_standard_processor,
)
from app.services.research_data.registry import ModelImmutabilityError
from app.services.research_data.contracts import DatasetDefinition


def _segments() -> SegmentSpec:
    return SegmentSpec(
        train=SegmentRange(start=date(2024, 1, 1), end=date(2024, 2, 29)),
        valid=SegmentRange(start=date(2024, 3, 1), end=date(2024, 4, 30)),
        test=SegmentRange(start=date(2024, 5, 1), end=date(2024, 6, 30)),
    )


def test_artifact_id_sensitive_to_seed_and_config():
    d = compute_config_digest({"a": 1})
    a = compute_model_artifact_id(
        bundle_hash="b1",
        model_ref="lgb_baseline@1",
        config_digest=d,
        seed=42,
    )
    b = compute_model_artifact_id(
        bundle_hash="b1",
        model_ref="lgb_baseline@1",
        config_digest=d,
        seed=43,
    )
    assert a != b


def test_registry_model_version_immutable(golden_qlib_env):
    registry = golden_qlib_env["registry"]
    registry.upsert_model(builtin_lgb_baseline_model())
    registry.upsert_model_version(
        ModelVersionRecord(
            model_code="lgb_baseline",
            version="1",
            config={"num_boost_round": 5},
        )
    )
    with pytest.raises(ModelImmutabilityError):
        registry.upsert_model_version(
            ModelVersionRecord(
                model_code="lgb_baseline",
                version="1",
                config={"num_boost_round": 99},
            )
        )


def _train_dataset_ref(golden_qlib_env, *, processor: str | None = None) -> str:
    registry = golden_qlib_env["registry"]
    query = golden_qlib_env["query"]
    handle = query.dataset(golden_qlib_env["dataset_ref"])
    base = handle.definition
    definition = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version="v1_2d",
        name="phase2d train",
        frequency="1d",
        universe_code=base.universe_code,
        universe_version=base.universe_version,
        snapshot_id=base.snapshot_id,
        schema_version=base.schema_version,
        features=base.features,
        price_policy=base.price_policy,
        processor=processor,
        pit=True,
    )
    registry.upsert_dataset(definition, status="validated")
    return f"{GOLDEN_DATASET_CODE}@v1_2d"


def test_train_predict_traceability(golden_qlib_env, tmp_path):
    pytest.importorskip("qlib")
    from app.services.research_data.model_training.adapter import lightgbm_runtime_available

    if not lightgbm_runtime_available():
        pytest.skip("lightgbm unavailable (install libomp on macOS)")
    registry = golden_qlib_env["registry"]
    registry.upsert_processor(builtin_qd_standard_processor())
    registry.upsert_model(builtin_lgb_baseline_model())
    dataset_ref = _train_dataset_ref(golden_qlib_env, processor="qd_standard@1")

    adapter = QlibAdapter(
        golden_qlib_env["query"],
        materializer=golden_qlib_env["materializer"],
        registry=registry,
        dataset_cache_root=tmp_path / "ds_cache",
        start=golden_qlib_env["start"],
        end=golden_qlib_env["end"],
    )
    from app.services.research_data.model_training.artifact_store import ModelArtifactStore

    store = ModelArtifactStore(root=tmp_path / "artifacts")
    trainer = ModelTrainer(adapter, registry, artifact_store=store)
    spec = ModelTrainSpec(
        dataset_spec=ResearchDatasetSpec(dataset_ref=dataset_ref, segments=_segments()),
        model=builtin_lgb_baseline_model(),
        seed=42,
    )
    r1 = trainer.train(spec)
    r2 = trainer.train(spec)

    assert r1.artifact_id == r2.artifact_id
    assert r1.predictions
    for p in r1.predictions:
        assert p.model_version == "lgb_baseline@1"
        assert p.dataset_hash == r1.dataset_hash
        assert p.bundle_hash == r1.bundle_hash

    meta = store.read_metadata(r1.artifact_id)
    assert meta["dataset_hash"] == r1.dataset_hash
    assert meta["processor_version"] == "qd_standard@1"

    art = registry.get_artifact(r1.artifact_id)
    assert isinstance(art, ArtifactRecord)
    assert art.artifact_type == "model"


def test_processor_change_changes_bundle_hash(golden_qlib_env, tmp_path):
    registry = golden_qlib_env["registry"]
    registry.upsert_processor(builtin_qd_standard_processor())
    ref_a = _train_dataset_ref(golden_qlib_env, processor="qd_standard@1")
    ref_b = _train_dataset_ref(golden_qlib_env, processor=None)
    # ref_b 需要不同 version
    handle = golden_qlib_env["query"].dataset(golden_qlib_env["dataset_ref"])
    base = handle.definition
    definition = DatasetDefinition(
        code=GOLDEN_DATASET_CODE,
        version="v1_2d_noproc",
        name="no proc",
        frequency="1d",
        universe_code=base.universe_code,
        universe_version=base.universe_version,
        snapshot_id=base.snapshot_id,
        schema_version=base.schema_version,
        features=base.features,
        price_policy=base.price_policy,
        processor=None,
        pit=True,
    )
    registry.upsert_dataset(definition, status="validated")
    ref_b = f"{GOLDEN_DATASET_CODE}@v1_2d_noproc"

    resolver = VersionResolver(golden_qlib_env["query"], registry)
    assert resolver.resolve(ref_a).bundle_hash != resolver.resolve(ref_b).bundle_hash
