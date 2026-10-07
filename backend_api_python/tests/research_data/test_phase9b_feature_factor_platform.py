"""Phase 9B — Feature / Factor Platform。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.research_data.contracts import FeatureDefinition, PricePolicy
from app.services.research_data.feature_factor_platform.hashing import compute_feature_set_hash
from app.services.research_data.feature_factor_platform.protocol import ENGINE_VERSION
from app.services.research_data.feature_factor_platform.runner import FeatureFactorPlatformError
from app.services.research_data.feature_factor_platform.feature_set import AlphaDefinition
from app.services.research_data.factor_lab.dependencies import FactorDependencyError
from feature_factor_platform_golden.golden import (
    GOLDEN_DATASET_REF,
    GOLDEN_FACTOR_REF,
    GOLDEN_FS_REF,
    build_window,
    compute_metadata_inject,
    golden_factor_definition,
    golden_feature_definition,
    golden_feature_set_definition,
    make_feature_factor_env,
)


def test_engine_version():
    assert ENGINE_VERSION == "qd_feature_factor_platform@1"


def test_taxonomy_wrong_layer(tmp_path):
    svc, _ds, _reg, _q, _c, _days = make_feature_factor_env(tmp_path / "tax")
    with pytest.raises(FeatureFactorPlatformError):
        svc.register_feature(golden_factor_definition())
    feat = golden_feature_definition()
    feat = feat.model_copy(update={"definition": {"asset_kind": "FEATURE"}})
    with pytest.raises(FeatureFactorPlatformError):
        svc.register_factor(feat)


def test_feature_set_hash_stable_and_member_change(tmp_path):
    svc, _ds, _reg, _q, _c, _days = make_feature_factor_env(tmp_path / "fsh")
    svc.register_factor(golden_factor_definition())
    d1 = golden_feature_set_definition()
    m1 = svc.register_feature_set(d1)
    m2 = svc.register_feature_set(d1)
    assert m1.feature_set_hash == m2.feature_set_hash
    d2 = golden_feature_set_definition(members=[GOLDEN_FACTOR_REF, "other@1.0.0"])
    d2 = d2.model_copy(update={"version": "1.0.1"})
    m3 = svc.register_feature_set(d2)
    assert m3.feature_set_hash != m1.feature_set_hash
    assert (
        compute_feature_set_hash(
            code=d1.code,
            version=d1.version,
            member_refs=d1.member_refs,
            processor=d1.processor,
            schema_version=d1.schema_version,
        )
        == m1.feature_set_hash
    )


def test_dag_missing_and_cycle(tmp_path):
    svc, _ds, reg, _q, _c, _days = make_feature_factor_env(tmp_path / "dag")
    svc.register_factor(golden_factor_definition())
    with pytest.raises(FeatureFactorPlatformError):
        svc.register_factor(
            FeatureDefinition(
                code="PHASE9B_BAD",
                version="1.0.0",
                name="bad",
                expression="x",
                dependencies=["factor:missing@9.9.9"],
            )
        )
    with pytest.raises(FactorDependencyError):
        from app.services.research_data.factor_lab import register_factor

        register_factor(
            reg,
            FeatureDefinition(
                code="PHASE9B_CYC",
                version="1.0.0",
                name="cyc",
                expression="x",
                dependencies=["factor:PHASE9B_CYC@1.0.0"],
                definition={"asset_kind": "FACTOR"},
            ),
        )


def test_build_factor_pins_dataset_and_immutable(tmp_path):
    svc, ds, _reg, _q, _c, days = make_feature_factor_env(tmp_path / "build")
    svc.register_factor(golden_factor_definition())
    window = build_window(days)
    br1 = svc.build_factor(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        window=window,
        inject=compute_metadata_inject(),
    )
    assert len(br1.factor_hash) == 64
    assert br1.dataset_hash == ds.get(GOLDEN_DATASET_REF).dataset_hash
    assert br1.build_index_uri
    assert Path(br1.build_index_uri).is_file()

    br2 = svc.build_factor(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        window=window,
        inject=compute_metadata_inject(),
    )
    assert br2.factor_dataset_id == br1.factor_dataset_id

    mutated = golden_factor_definition()
    mutated = mutated.model_copy(
        update={"definition": {**(mutated.definition or {}), "factor_pipeline": {"direction": "short"}}}
    )
    with pytest.raises(FeatureFactorPlatformError):
        svc.register_factor(mutated)


def test_lineage_and_list_by_dataset(tmp_path):
    svc, ds, _reg, _q, _c, days = make_feature_factor_env(tmp_path / "lin")
    svc.register_factor(golden_factor_definition())
    window = build_window(days)
    br = svc.build_factor(
        GOLDEN_FACTOR_REF,
        GOLDEN_DATASET_REF,
        window=window,
        inject=compute_metadata_inject(),
    )
    lin = svc.get_lineage(GOLDEN_FACTOR_REF, dataset_ref=GOLDEN_DATASET_REF)
    assert lin.ref == GOLDEN_FACTOR_REF
    assert any(c.kind == "DATASET" for c in lin.children)
    refs = svc.list_by_dataset(br.dataset_hash)
    assert GOLDEN_FACTOR_REF in refs


def test_alpha_register_only(tmp_path):
    svc, _ds, _reg, _q, _c, _days = make_feature_factor_env(tmp_path / "alpha")
    svc.register_factor(golden_factor_definition())
    alpha = AlphaDefinition(
        code="PHASE9B_ALPHA",
        version="1.0.0",
        name="demo alpha",
        expression="0.5 * mom",
        factor_refs=[GOLDEN_FACTOR_REF],
        weights={GOLDEN_FACTOR_REF: 0.5},
    )
    feat = svc.register_alpha(alpha)
    assert feat.definition.get("asset_kind") == "ALPHA"
    with pytest.raises(FeatureFactorPlatformError):
        svc.build_factor(
            f"{alpha.code}@{alpha.version}",
            GOLDEN_DATASET_REF,
            window=("2024-05-06", "2024-05-10"),
        )


def test_no_mining_eval_apis():
    from app.services.research_data.feature_factor_platform.runner import FeatureFactorService

    forbidden = ("mine_factors", "evaluate_ic", "train_model", "promote")
    for name in forbidden:
        assert not hasattr(FeatureFactorService, name)


def test_package_no_trading_db_imports():
    root = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "research_data"
        / "feature_factor_platform"
    )
    forbidden = ("trading_db", "submit_order", "production_oms", "psycopg")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for tok in forbidden:
            assert tok not in text, f"{path.name} contains {tok}"


def test_build_feature_set(tmp_path):
    svc, _ds, _reg, _q, _c, days = make_feature_factor_env(tmp_path / "bfs")
    svc.register_factor(golden_factor_definition())
    svc.register_feature_set(golden_feature_set_definition())
    window = build_window(days)
    result = svc.build_feature_set(
        GOLDEN_FS_REF,
        GOLDEN_DATASET_REF,
        window=window,
        inject=compute_metadata_inject(),
    )
    assert result.member_builds
    assert Path(result.build_index_uri).is_file()
